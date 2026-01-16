from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from enum import Enum
import logging
import asyncio
from functools import partial

logger = logging.getLogger(__name__)

from ..database import get_db
from ..models.financial import Stock, BalanceSheet, IncomeStatement, CashFlowStatement, PeriodType
from ..schemas.financial import (
    StockResponse,
    BalanceSheetResponse,
    IncomeStatementResponse,
    CashFlowStatementResponse,
    FinancialReportResponse,
    FetchDataRequest,
    FetchDataResponse,
    PeriodType as PeriodTypeSchema,
)
from ..services.vnstock_service import VnstockService
from ..services.pdf_scraper import PDFScraper
from ..services.scheduler import get_scheduler_status, trigger_manual_update

router = APIRouter()


class Language(str, Enum):
    EN = "en"
    VI = "vi"


class DataSource(str, Enum):
    AUTO = "auto"
    PDF = "pdf"
    VNSTOCK = "vnstock"


# In-memory fetch status tracking
_fetch_status: dict = {}


def get_fetch_status(symbol: str) -> str:
    """Get fetch status for a symbol."""
    return _fetch_status.get(symbol.upper(), "idle")


def set_fetch_status(symbol: str, status: str):
    """Set fetch status for a symbol."""
    _fetch_status[symbol.upper()] = status


@router.get("/stocks", response_model=List[StockResponse])
async def list_stocks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List all stocks in the database."""
    stocks = db.query(Stock).offset(skip).limit(limit).all()
    return stocks


@router.get("/stocks/search")
async def search_stocks(
    q: str = Query(..., min_length=1, description="Search query"),
    db: Session = Depends(get_db),
):
    """Search for stocks by symbol or name using vnstock."""
    service = VnstockService(db)
    results = service.search_stocks(q)
    return results


@router.get("/stocks/{symbol}", response_model=StockResponse)
async def get_stock(
    symbol: str,
    db: Session = Depends(get_db),
):
    """Get stock details by symbol."""
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")
    return stock


@router.get("/stocks/{symbol}/status")
async def get_stock_status(symbol: str):
    """Get the fetch status for a stock."""
    return {"symbol": symbol.upper(), "status": get_fetch_status(symbol)}


def delete_existing_data(symbol: str, period_type: str, db: Session) -> int:
    """Delete existing financial data for a symbol. Returns count of deleted records."""
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        return 0

    period_enum = PeriodType(period_type)
    deleted = 0

    deleted += db.query(BalanceSheet).filter(
        BalanceSheet.stock_id == stock.id,
        BalanceSheet.period_type == period_enum,
    ).delete()

    deleted += db.query(IncomeStatement).filter(
        IncomeStatement.stock_id == stock.id,
        IncomeStatement.period_type == period_enum,
    ).delete()

    deleted += db.query(CashFlowStatement).filter(
        CashFlowStatement.stock_id == stock.id,
        CashFlowStatement.period_type == period_enum,
    ).delete()

    db.commit()
    return deleted


def fetch_from_pdf(symbol: str, period_type: str, years: int, db: Session) -> dict:
    """Fetch data from PDF reports using OCR."""
    scraper = PDFScraper(db)
    return scraper.fetch_financial_reports(
        symbol=symbol,
        period_type=period_type,
        years=years,
    )


def fetch_from_vnstock(symbol: str, period_type: str, years: int, lang: str, db: Session) -> dict:
    """Fetch data from vnstock."""
    service = VnstockService(db)
    return service.fetch_and_store_financial_data(
        symbol=symbol,
        period_type=period_type,
        years=years,
        lang=lang,
    )


@router.post("/stocks/{symbol}/fetch", response_model=FetchDataResponse)
async def fetch_stock_data(
    symbol: str,
    background_tasks: BackgroundTasks,
    request: FetchDataRequest = None,
    lang: Language = Query(Language.VI, description="Language: en or vi"),
    source: DataSource = Query(DataSource.AUTO, description="Data source: auto, pdf, or vnstock"),
    force: bool = Query(False, description="Force update: delete existing data and re-fetch"),
    db: Session = Depends(get_db),
):
    """
    Fetch and store financial data.

    - source=auto: Try vnstock first, fallback to PDF scraping
    - source=pdf: Only use PDF scraping with OCR
    - source=vnstock: Only use vnstock API
    - force=true: Delete existing data before fetching (force update)
    """
    if request is None:
        request = FetchDataRequest()

    symbol = symbol.upper()
    set_fetch_status(symbol, "fetching")

    # Force update: delete existing data first
    if force:
        deleted = delete_existing_data(symbol, request.period_type.value, db)
        if deleted > 0:
            logger.info(f"Force update: deleted {deleted} existing records for {symbol}")

    result = None
    used_source = None

    # Run blocking operations in thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()

    try:
        if source == DataSource.PDF:
            result = await loop.run_in_executor(
                None,
                partial(fetch_from_pdf, symbol, request.period_type.value, request.years, db)
            )
            used_source = "pdf"
        elif source == DataSource.VNSTOCK:
            result = await loop.run_in_executor(
                None,
                partial(fetch_from_vnstock, symbol, request.period_type.value, request.years, lang.value, db)
            )
            used_source = "vnstock"
        else:
            # Auto: Try vnstock first (faster, more reliable), fallback to PDF scraping
            try:
                result = await loop.run_in_executor(
                    None,
                    partial(fetch_from_vnstock, symbol, request.period_type.value, request.years, lang.value, db)
                )
                total_added = (
                    result["balance_sheets_count"] +
                    result["income_statements_count"] +
                    result["cash_flow_statements_count"]
                )
                if total_added > 0:
                    used_source = "vnstock"
                else:
                    raise ValueError("No data from vnstock")
            except Exception:
                result = await loop.run_in_executor(
                    None,
                    partial(fetch_from_pdf, symbol, request.period_type.value, request.years, db)
                )
                used_source = "pdf"

        set_fetch_status(symbol, "completed")

    except ValueError as e:
        set_fetch_status(symbol, "error")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        set_fetch_status(symbol, "error")
        raise HTTPException(status_code=500, detail=f"Failed to fetch data: {str(e)}")

    return FetchDataResponse(
        message=f"Successfully fetched data for {symbol} from {used_source}",
        stock=StockResponse.model_validate(result["stock"]),
        balance_sheets_count=result["balance_sheets_count"],
        income_statements_count=result["income_statements_count"],
        cash_flow_statements_count=result["cash_flow_statements_count"],
    )


@router.get("/stocks/{symbol}/balance-sheet", response_model=List[BalanceSheetResponse])
async def get_balance_sheets(
    symbol: str,
    year: Optional[int] = Query(None, description="Filter by year"),
    period_type: Optional[PeriodTypeSchema] = Query(None, description="Filter by period type"),
    db: Session = Depends(get_db),
):
    """Get balance sheets for a stock."""
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

    query = db.query(BalanceSheet).filter(BalanceSheet.stock_id == stock.id)

    if year:
        query = query.filter(BalanceSheet.year == year)
    if period_type:
        query = query.filter(BalanceSheet.period_type == PeriodType(period_type.value))

    balance_sheets = query.order_by(BalanceSheet.year.desc(), BalanceSheet.quarter.desc()).all()
    return balance_sheets


@router.get("/stocks/{symbol}/income-statement", response_model=List[IncomeStatementResponse])
async def get_income_statements(
    symbol: str,
    year: Optional[int] = Query(None, description="Filter by year"),
    period_type: Optional[PeriodTypeSchema] = Query(None, description="Filter by period type"),
    db: Session = Depends(get_db),
):
    """Get income statements for a stock."""
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

    query = db.query(IncomeStatement).filter(IncomeStatement.stock_id == stock.id)

    if year:
        query = query.filter(IncomeStatement.year == year)
    if period_type:
        query = query.filter(IncomeStatement.period_type == PeriodType(period_type.value))

    income_statements = query.order_by(IncomeStatement.year.desc(), IncomeStatement.quarter.desc()).all()
    return income_statements


@router.get("/stocks/{symbol}/cash-flow", response_model=List[CashFlowStatementResponse])
async def get_cash_flow_statements(
    symbol: str,
    year: Optional[int] = Query(None, description="Filter by year"),
    period_type: Optional[PeriodTypeSchema] = Query(None, description="Filter by period type"),
    db: Session = Depends(get_db),
):
    """Get cash flow statements for a stock."""
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

    query = db.query(CashFlowStatement).filter(CashFlowStatement.stock_id == stock.id)

    if year:
        query = query.filter(CashFlowStatement.year == year)
    if period_type:
        query = query.filter(CashFlowStatement.period_type == PeriodType(period_type.value))

    cash_flows = query.order_by(CashFlowStatement.year.desc(), CashFlowStatement.quarter.desc()).all()
    return cash_flows


@router.get("/stocks/{symbol}/reports")
async def get_all_reports(
    symbol: str,
    background_tasks: BackgroundTasks,
    year: Optional[int] = Query(None, description="Filter by year"),
    period_type: PeriodTypeSchema = Query(PeriodTypeSchema.ANNUAL, description="Period type"),
    lang: Language = Query(Language.VI, description="Language: en or vi"),
    auto_fetch: bool = Query(True, description="Auto fetch if no data in DB"),
    source: DataSource = Query(DataSource.AUTO, description="Data source for auto fetch"),
    db: Session = Depends(get_db),
):
    """Get all financial reports for a stock. Auto-fetches from API if not in DB."""
    symbol = symbol.upper()
    stock = db.query(Stock).filter(Stock.symbol == symbol).first()

    period_type_enum = PeriodType(period_type.value)

    # Run blocking operations in thread pool
    loop = asyncio.get_event_loop()

    # If stock not in DB or no data, trigger fetch
    if not stock:
        if auto_fetch:
            # Create stock and fetch data
            set_fetch_status(symbol, "fetching")
            try:
                if source == DataSource.PDF:
                    result = await loop.run_in_executor(
                        None, partial(fetch_from_pdf, symbol, period_type.value, 10, db)
                    )
                elif source == DataSource.VNSTOCK:
                    result = await loop.run_in_executor(
                        None, partial(fetch_from_vnstock, symbol, period_type.value, 10, lang.value, db)
                    )
                else:
                    # Auto: Try vnstock first (faster, more reliable)
                    try:
                        result = await loop.run_in_executor(
                            None, partial(fetch_from_vnstock, symbol, period_type.value, 10, lang.value, db)
                        )
                        total = result["balance_sheets_count"] + result["income_statements_count"] + result["cash_flow_statements_count"]
                        if total == 0:
                            raise ValueError("No data from vnstock")
                    except Exception:
                        result = await loop.run_in_executor(
                            None, partial(fetch_from_pdf, symbol, period_type.value, 10, db)
                        )

                set_fetch_status(symbol, "completed")
                stock = db.query(Stock).filter(Stock.symbol == symbol).first()
            except Exception as e:
                set_fetch_status(symbol, "error")
                raise HTTPException(status_code=400, detail=f"Failed to fetch data: {str(e)}")
        else:
            return {
                "stock": None,
                "balance_sheets": [],
                "income_statements": [],
                "cash_flow_statements": [],
                "status": "not_found",
                "message": "Stock not in database. Set auto_fetch=true to fetch from API.",
            }

    # Get balance sheets
    bs_query = db.query(BalanceSheet).filter(
        BalanceSheet.stock_id == stock.id,
        BalanceSheet.period_type == period_type_enum,
    )
    if year:
        bs_query = bs_query.filter(BalanceSheet.year == year)
    balance_sheets = bs_query.order_by(BalanceSheet.year.desc(), BalanceSheet.quarter.desc()).all()

    # Get income statements
    is_query = db.query(IncomeStatement).filter(
        IncomeStatement.stock_id == stock.id,
        IncomeStatement.period_type == period_type_enum,
    )
    if year:
        is_query = is_query.filter(IncomeStatement.year == year)
    income_statements = is_query.order_by(IncomeStatement.year.desc(), IncomeStatement.quarter.desc()).all()

    # Get cash flow statements
    cf_query = db.query(CashFlowStatement).filter(
        CashFlowStatement.stock_id == stock.id,
        CashFlowStatement.period_type == period_type_enum,
    )
    if year:
        cf_query = cf_query.filter(CashFlowStatement.year == year)
    cash_flows = cf_query.order_by(CashFlowStatement.year.desc(), CashFlowStatement.quarter.desc()).all()

    # If no data found and auto_fetch enabled, fetch in background
    has_data = len(balance_sheets) > 0 or len(income_statements) > 0 or len(cash_flows) > 0
    status = "loaded" if has_data else "no_data"

    if not has_data and auto_fetch and get_fetch_status(symbol) != "fetching":
        # Trigger fetch in thread pool (non-blocking)
        set_fetch_status(symbol, "fetching")
        try:
            if source == DataSource.PDF:
                await loop.run_in_executor(
                    None, partial(fetch_from_pdf, symbol, period_type.value, 10, db)
                )
            elif source == DataSource.VNSTOCK:
                await loop.run_in_executor(
                    None, partial(fetch_from_vnstock, symbol, period_type.value, 10, lang.value, db)
                )
            else:
                try:
                    result = await loop.run_in_executor(
                        None, partial(fetch_from_vnstock, symbol, period_type.value, 10, lang.value, db)
                    )
                    total = result["balance_sheets_count"] + result["income_statements_count"] + result["cash_flow_statements_count"]
                    if total == 0:
                        raise ValueError("No data from vnstock")
                except Exception:
                    await loop.run_in_executor(
                        None, partial(fetch_from_pdf, symbol, period_type.value, 10, db)
                    )

            set_fetch_status(symbol, "completed")
            # Reload data
            balance_sheets = bs_query.all()
            income_statements = is_query.all()
            cash_flows = cf_query.all()
            status = "loaded"
        except Exception as e:
            set_fetch_status(symbol, "error")
            status = "fetch_error"

    return {
        "stock": StockResponse.model_validate(stock) if stock else None,
        "balance_sheets": [BalanceSheetResponse.model_validate(bs) for bs in balance_sheets],
        "income_statements": [IncomeStatementResponse.model_validate(inc) for inc in income_statements],
        "cash_flow_statements": [CashFlowStatementResponse.model_validate(cf) for cf in cash_flows],
        "status": status,
        "fetch_status": get_fetch_status(symbol),
    }


@router.delete("/stocks/{symbol}")
async def delete_stock(
    symbol: str,
    db: Session = Depends(get_db),
):
    """Delete a stock and all its financial data."""
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

    db.delete(stock)
    db.commit()
    set_fetch_status(symbol, "idle")

    return {"message": f"Successfully deleted {symbol.upper()} and all associated data"}


# Scheduler endpoints
@router.get("/scheduler/status")
async def scheduler_status():
    """Get the current scheduler status."""
    return get_scheduler_status()


@router.post("/scheduler/trigger")
async def trigger_scheduler(
    symbols: Optional[List[str]] = Query(None, description="Stock symbols to update. If empty, updates all stocks."),
):
    """
    Manually trigger the data update job.

    - If symbols provided: Updates only those stocks
    - If no symbols: Updates all stocks in database
    """
    result = await trigger_manual_update(symbols)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result
