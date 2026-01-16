"""Scheduler service for automated data updates."""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.financial import Stock
from .pdf_scraper import PDFScraper
from .vnstock_service import VnstockService, VN50_SYMBOLS

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None
_is_running: bool = False
_last_run: Optional[datetime] = None
_last_status: str = "idle"
_vn50_sync_done: bool = False

# Rate limiting retry configuration
RATE_LIMIT_RETRY_DELAY = 45  # seconds to wait before retrying after rate limit
MAX_RETRY_ATTEMPTS = 3  # maximum retry attempts per symbol
_retry_queue: Dict[str, Dict[str, Any]] = {}  # {symbol: {"attempts": int, "period_type": str, ...}}


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="Asia/Ho_Chi_Minh")
    return _scheduler


def is_rate_limit_error(error: Exception) -> bool:
    """Check if an error is a rate limit error from vnstock/VCI."""
    error_msg = str(error).lower()
    return any(phrase in error_msg for phrase in [
        "rate limit",
        "quá nhiều request",
        "vui lòng thử lại sau",
        "too many requests",
    ])


def add_to_retry_queue(symbol: str, period_type: str = "annual", years: int = 6, lang: str = "vi"):
    """Add a symbol to the retry queue for later processing."""
    global _retry_queue
    if symbol in _retry_queue:
        _retry_queue[symbol]["attempts"] += 1
    else:
        _retry_queue[symbol] = {
            "attempts": 1,
            "period_type": period_type,
            "years": years,
            "lang": lang,
            "added_at": datetime.now(),
        }
    logger.info(f"Added {symbol} to retry queue (attempt {_retry_queue[symbol]['attempts']})")


def remove_from_retry_queue(symbol: str):
    """Remove a symbol from the retry queue."""
    global _retry_queue
    if symbol in _retry_queue:
        del _retry_queue[symbol]


def get_retry_queue_status() -> dict:
    """Get the current retry queue status."""
    return {
        "queue_size": len(_retry_queue),
        "symbols": list(_retry_queue.keys()),
        "details": {
            symbol: {
                "attempts": info["attempts"],
                "added_at": info["added_at"].isoformat(),
            }
            for symbol, info in _retry_queue.items()
        },
    }


def get_scheduler_status() -> dict:
    """Get current scheduler status."""
    global _is_running, _last_run, _last_status
    scheduler = get_scheduler()
    return {
        "is_running": scheduler.running,
        "is_job_running": _is_running,
        "last_run": _last_run.isoformat() if _last_run else None,
        "last_status": _last_status,
        "retry_queue": get_retry_queue_status(),
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in scheduler.get_jobs()
        ],
    }


async def process_retry_queue():
    """Process symbols in the retry queue after rate limit delay."""
    global _retry_queue

    if not _retry_queue:
        logger.debug("Retry queue is empty")
        return

    logger.info(f"Processing retry queue: {len(_retry_queue)} symbols")

    db = SessionLocal()
    processed = []

    try:
        for symbol, info in list(_retry_queue.items()):
            if info["attempts"] >= MAX_RETRY_ATTEMPTS:
                logger.warning(f"Max retry attempts reached for {symbol}, removing from queue")
                processed.append(symbol)
                continue

            try:
                service = VnstockService(db)
                result = service.fetch_and_store_financial_data(
                    symbol=symbol,
                    period_type=info["period_type"],
                    years=info["years"],
                    lang=info["lang"],
                    timeout=60,
                )

                total = (
                    result["balance_sheets_count"] +
                    result["income_statements_count"] +
                    result["cash_flow_statements_count"]
                )

                if total > 0:
                    logger.info(f"Retry successful for {symbol}: {total} records")
                    processed.append(symbol)
                else:
                    logger.warning(f"Retry for {symbol}: no data returned")
                    processed.append(symbol)

            except Exception as e:
                if is_rate_limit_error(e):
                    # Still rate limited, increment attempts and schedule another retry
                    _retry_queue[symbol]["attempts"] += 1
                    logger.warning(f"Still rate limited for {symbol}, will retry later (attempt {_retry_queue[symbol]['attempts']})")
                    schedule_retry_job()
                    break  # Stop processing queue, wait for rate limit to clear
                else:
                    logger.error(f"Retry failed for {symbol}: {e}")
                    processed.append(symbol)

            # Small delay between retries
            await asyncio.sleep(2)

        # Remove successfully processed symbols from queue
        for symbol in processed:
            remove_from_retry_queue(symbol)

    except Exception as e:
        logger.error(f"Error processing retry queue: {e}")
    finally:
        db.close()


def schedule_retry_job():
    """Schedule a job to process the retry queue after the rate limit delay."""
    scheduler = get_scheduler()

    # Check if retry job already scheduled
    existing_job = scheduler.get_job("retry_queue_job")
    if existing_job:
        logger.debug("Retry job already scheduled")
        return

    run_time = datetime.now() + timedelta(seconds=RATE_LIMIT_RETRY_DELAY)
    scheduler.add_job(
        process_retry_queue,
        trigger=DateTrigger(run_date=run_time),
        id="retry_queue_job",
        name="Retry Queue Processing",
        replace_existing=True,
    )
    logger.info(f"Scheduled retry job for {run_time.strftime('%H:%M:%S')} ({RATE_LIMIT_RETRY_DELAY}s from now)")


async def update_stock_data(symbol: str, db: Session, period_type: str = "annual", years: int = 6, lang: str = "vi") -> dict:
    """
    Update financial data for a single stock.

    Tries vnstock API first (faster, more reliable), then falls back to PDF scraping.
    Handles rate limiting by adding to retry queue.
    """
    result = {
        "symbol": symbol,
        "source": None,
        "success": False,
        "balance_sheets": 0,
        "income_statements": 0,
        "cash_flow_statements": 0,
        "error": None,
        "rate_limited": False,
    }

    # Try vnstock API first (faster, more reliable)
    try:
        service = VnstockService(db)
        vnstock_result = service.fetch_and_store_financial_data(
            symbol=symbol,
            period_type=period_type,
            years=years,
            lang=lang,
        )

        total_added = (
            vnstock_result["balance_sheets_count"] +
            vnstock_result["income_statements_count"] +
            vnstock_result["cash_flow_statements_count"]
        )

        if total_added > 0:
            result["source"] = "vnstock"
            result["success"] = True
            result["balance_sheets"] = vnstock_result["balance_sheets_count"]
            result["income_statements"] = vnstock_result["income_statements_count"]
            result["cash_flow_statements"] = vnstock_result["cash_flow_statements_count"]
            # Remove from retry queue if successful
            remove_from_retry_queue(symbol)
            logger.info(f"Updated {symbol} from vnstock: {total_added} records")
            return result
    except Exception as e:
        if is_rate_limit_error(e):
            # Add to retry queue and schedule retry
            add_to_retry_queue(symbol, period_type, years, lang)
            schedule_retry_job()
            result["rate_limited"] = True
            result["error"] = "Rate limited, added to retry queue"
            logger.warning(f"Rate limited for {symbol}, added to retry queue")
            return result
        else:
            logger.warning(f"vnstock fetch failed for {symbol}: {e}")

    # Fallback to PDF scraping with OCR
    try:
        scraper = PDFScraper(db)
        pdf_result = scraper.fetch_financial_reports(
            symbol=symbol,
            period_type="annual",
            years=6,
        )

        result["source"] = "pdf"
        result["success"] = True
        result["balance_sheets"] = pdf_result["balance_sheets_count"]
        result["income_statements"] = pdf_result["income_statements_count"]
        result["cash_flow_statements"] = pdf_result["cash_flow_statements_count"]
        logger.info(f"Updated {symbol} from PDF scraping")
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Failed to update {symbol}: {e}")

    return result


async def update_all_stocks():
    """
    Update financial data for all stocks in the database.

    This is the main scheduled job that runs daily.
    """
    global _is_running, _last_run, _last_status

    if _is_running:
        logger.warning("Update job is already running, skipping")
        return

    _is_running = True
    _last_run = datetime.now()
    _last_status = "running"

    logger.info("Starting scheduled update for all stocks")

    db = SessionLocal()
    try:
        # Get all stocks from database
        stocks: List[Stock] = db.query(Stock).all()

        if not stocks:
            logger.info("No stocks in database to update")
            _last_status = "completed (no stocks)"
            return

        results = []
        for stock in stocks:
            try:
                result = await update_stock_data(stock.symbol, db)
                results.append(result)
            except Exception as e:
                logger.error(f"Error updating {stock.symbol}: {e}")
                results.append({
                    "symbol": stock.symbol,
                    "success": False,
                    "error": str(e),
                })

        # Summarize results
        success_count = sum(1 for r in results if r.get("success"))
        fail_count = len(results) - success_count

        _last_status = f"completed: {success_count} success, {fail_count} failed"
        logger.info(f"Scheduled update completed: {success_count}/{len(results)} stocks updated")

    except Exception as e:
        _last_status = f"error: {str(e)}"
        logger.error(f"Scheduled update failed: {e}")
    finally:
        db.close()
        _is_running = False


async def trigger_manual_update(symbols: Optional[List[str]] = None) -> dict:
    """
    Trigger a manual update for specified stocks or all stocks.

    Args:
        symbols: List of stock symbols to update. If None, updates all stocks.

    Returns:
        Dictionary with update results
    """
    global _is_running, _last_run, _last_status

    if _is_running:
        return {
            "success": False,
            "message": "Update job is already running",
        }

    _is_running = True
    _last_run = datetime.now()
    _last_status = "running (manual)"

    db = SessionLocal()
    results = []

    try:
        if symbols:
            # Update specific stocks
            for symbol in symbols:
                result = await update_stock_data(symbol.upper(), db)
                results.append(result)
        else:
            # Update all stocks in database
            stocks: List[Stock] = db.query(Stock).all()
            for stock in stocks:
                result = await update_stock_data(stock.symbol, db)
                results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        _last_status = f"completed (manual): {success_count}/{len(results)} success"

        return {
            "success": True,
            "message": f"Updated {success_count}/{len(results)} stocks",
            "results": results,
        }
    except Exception as e:
        _last_status = f"error (manual): {str(e)}"
        return {
            "success": False,
            "message": str(e),
            "results": results,
        }
    finally:
        db.close()
        _is_running = False


async def sync_vn50_symbols():
    """
    Sync VN50 symbols to database on startup.
    This ensures popular stocks are pre-loaded for faster search/filter.
    Uses retry queue for rate-limited symbols.
    """
    global _vn50_sync_done

    if _vn50_sync_done:
        logger.info("VN50 sync already completed")
        return

    # Only sync first 10 symbols on startup to avoid rate limiting
    # Full sync can be done via manual trigger
    symbols_to_sync = VN50_SYMBOLS[:10]
    logger.info(f"Starting VN50 sync: {len(symbols_to_sync)} symbols (first batch)")

    db = SessionLocal()
    synced = 0
    skipped = 0
    rate_limited_count = 0

    try:
        for symbol in symbols_to_sync:
            # Check if stock already exists in DB with data
            existing = db.query(Stock).filter(Stock.symbol == symbol).first()
            if existing:
                skipped += 1
                continue

            # Sync stock data
            try:
                service = VnstockService(db)
                result = service.fetch_and_store_financial_data(
                    symbol=symbol,
                    period_type="annual",
                    years=6,
                    lang="vi",
                    timeout=60,
                )
                total = (
                    result["balance_sheets_count"] +
                    result["income_statements_count"] +
                    result["cash_flow_statements_count"]
                )
                if total > 0:
                    synced += 1
                    logger.info(f"Synced {symbol}: {total} records")
                else:
                    logger.warning(f"No data for {symbol}")
            except Exception as e:
                if is_rate_limit_error(e):
                    # Add remaining symbols to retry queue
                    rate_limited_count += 1
                    add_to_retry_queue(symbol, "annual", 6, "vi")
                    logger.warning(f"Rate limited at {symbol}, added to retry queue")
                    # Add remaining symbols to queue as well
                    current_idx = symbols_to_sync.index(symbol)
                    for remaining_symbol in symbols_to_sync[current_idx + 1:]:
                        if not db.query(Stock).filter(Stock.symbol == remaining_symbol).first():
                            add_to_retry_queue(remaining_symbol, "annual", 6, "vi")
                            rate_limited_count += 1
                    # Schedule retry
                    schedule_retry_job()
                    break
                else:
                    logger.warning(f"Failed to sync {symbol}: {e}")

            # Longer delay to avoid rate limiting (3 seconds between requests)
            await asyncio.sleep(3)

        _vn50_sync_done = True
        logger.info(f"VN50 sync completed: {synced} synced, {skipped} skipped, {rate_limited_count} queued for retry")

    except Exception as e:
        logger.error(f"VN50 sync failed: {e}")
    finally:
        db.close()


def start_scheduler():
    """Start the scheduler with the daily update job."""
    scheduler = get_scheduler()

    if scheduler.running:
        logger.info("Scheduler is already running")
        return

    # Add the daily update job
    # Run at 6:00 PM Vietnam time (after market close)
    scheduler.add_job(
        update_all_stocks,
        trigger=CronTrigger(hour=18, minute=0, timezone="Asia/Ho_Chi_Minh"),
        id="daily_update",
        name="Daily Financial Data Update",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with daily update job at 6:00 PM Vietnam time")


def shutdown_scheduler():
    """Shutdown the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
