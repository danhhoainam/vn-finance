from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import logging
import signal
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import time

from vnstock import Vnstock

from ..models.financial import (
    Stock,
    BalanceSheet,
    IncomeStatement,
    CashFlowStatement,
    PeriodType,
)

logger = logging.getLogger(__name__)

# Default timeout in seconds
DEFAULT_TIMEOUT = 30

# Cache configuration
CACHE_TTL = 300  # 5 minutes
_search_cache: Dict[str, Dict[str, Any]] = {}  # {query: {"results": [...], "timestamp": ...}}
_all_symbols_cache: Dict[str, Any] = {"data": None, "timestamp": 0}  # Cache for all symbols from API


def clear_search_cache():
    """Clear all search caches."""
    global _search_cache, _all_symbols_cache
    _search_cache = {}
    _all_symbols_cache = {"data": None, "timestamp": 0}
    logger.info("Search cache cleared")

# VN50 symbols list (top 50 Vietnam stocks by market cap)
VN50_SYMBOLS = [
    "VNM", "VCB", "VHM", "VIC", "BID", "CTG", "GAS", "HPG", "MSN", "MBB",
    "FPT", "SAB", "TCB", "VPB", "PLX", "NVL", "VRE", "BCM", "MWG", "SSI",
    "STB", "POW", "HDB", "TPB", "ACB", "VJC", "GVR", "SHB", "BVH", "VIB",
    "SSB", "PDR", "KDH", "LPB", "VCI", "REE", "EIB", "DCM", "DPM", "GMD",
    "HSG", "HCM", "DGC", "PNJ", "DHG", "VND", "PC1", "GEX", "SBT", "VCG",
]


def run_with_timeout(func, timeout: int = DEFAULT_TIMEOUT, *args, **kwargs):
    """Run a function with timeout using ThreadPoolExecutor."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            raise TimeoutError(f"Operation timed out after {timeout} seconds")
        except SystemExit as e:
            # vnstock raises SystemExit on rate limit
            raise ValueError(f"Rate limit exceeded: {e}")


class VnstockService:
    """Service for fetching financial data from vnstock."""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_stock(self, symbol: str) -> Stock:
        """Get existing stock or create a new one."""
        symbol = symbol.upper()
        stock = self.db.query(Stock).filter(Stock.symbol == symbol).first()

        if not stock:
            # Try to get stock info from vnstock
            try:
                vs = Vnstock().stock(symbol=symbol, source="VCI")
                company_info = vs.company.overview()
                if company_info is not None and not company_info.empty:
                    name = company_info.get("short_name", [None])[0] if "short_name" in company_info.columns else None
                    exchange = company_info.get("exchange", [None])[0] if "exchange" in company_info.columns else None
                else:
                    name = None
                    exchange = None
            except Exception as e:
                logger.warning(f"Could not fetch company info for {symbol}: {e}")
                name = None
                exchange = None

            stock = Stock(symbol=symbol, name=name, exchange=exchange)
            self.db.add(stock)
            self.db.commit()
            self.db.refresh(stock)

        return stock

    def fetch_and_store_financial_data(
        self,
        symbol: str,
        period_type: str = "annual",
        years: int = 6,  # From 2019 to now
        lang: str = "vi",  # Vietnamese by default
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """Fetch financial data from vnstock and store in database."""
        symbol = symbol.upper()
        stock = self.get_or_create_stock(symbol)

        try:
            def init_vnstock():
                return Vnstock().stock(symbol=symbol, source="VCI")

            vs = run_with_timeout(init_vnstock, timeout)
        except TimeoutError as e:
            logger.error(f"Timeout initializing vnstock for {symbol}: {e}")
            raise ValueError(f"Timeout fetching data for {symbol}")
        except Exception as e:
            logger.error(f"Failed to initialize vnstock for {symbol}: {e}")
            raise ValueError(f"Invalid stock symbol: {symbol}")

        # Determine period for vnstock
        period = "year" if period_type == "annual" else "quarter"
        period_enum = PeriodType.ANNUAL if period_type == "annual" else PeriodType.QUARTER

        balance_sheets_added = 0
        income_statements_added = 0
        cash_flow_statements_added = 0

        # Fetch Balance Sheet
        try:
            def fetch_balance():
                return vs.finance.balance_sheet(period=period, lang=lang)

            balance_data = run_with_timeout(fetch_balance, timeout)
            if balance_data is not None and not balance_data.empty:
                balance_sheets_added = self._store_balance_sheets(
                    stock, balance_data, period_enum, years
                )
        except TimeoutError:
            logger.warning(f"Timeout fetching balance sheet for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to fetch balance sheet for {symbol}: {e}")

        # Fetch Income Statement
        try:
            def fetch_income():
                return vs.finance.income_statement(period=period, lang=lang)

            income_data = run_with_timeout(fetch_income, timeout)
            if income_data is not None and not income_data.empty:
                income_statements_added = self._store_income_statements(
                    stock, income_data, period_enum, years
                )
        except TimeoutError:
            logger.warning(f"Timeout fetching income statement for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to fetch income statement for {symbol}: {e}")

        # Fetch Cash Flow Statement
        try:
            def fetch_cashflow():
                return vs.finance.cash_flow(period=period, lang=lang)

            cashflow_data = run_with_timeout(fetch_cashflow, timeout)
            if cashflow_data is not None and not cashflow_data.empty:
                cash_flow_statements_added = self._store_cash_flow_statements(
                    stock, cashflow_data, period_enum, years
                )
        except TimeoutError:
            logger.warning(f"Timeout fetching cash flow for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to fetch cash flow for {symbol}: {e}")

        return {
            "stock": stock,
            "balance_sheets_count": balance_sheets_added,
            "income_statements_count": income_statements_added,
            "cash_flow_statements_count": cash_flow_statements_added,
        }

    def _get_column_value(self, row: Dict, possible_names: List[str]) -> Optional[float]:
        """Get value from row using multiple possible column names."""
        for name in possible_names:
            if name in row and row[name] is not None:
                try:
                    value = float(row[name])
                    return value if not (value != value) else None  # Check for NaN
                except (ValueError, TypeError):
                    continue
        return None

    def _parse_period(self, row_dict: Dict) -> tuple:
        """Parse year and quarter from data."""
        try:
            # Try different column names for year (including Vietnamese)
            year_val = (row_dict.get("year") or row_dict.get("yearReport") or
                       row_dict.get("Year") or row_dict.get("Năm"))
            quarter_val = (row_dict.get("quarter") or row_dict.get("lengthReport") or
                          row_dict.get("Quarter") or row_dict.get("Quý") or row_dict.get("Kỳ"))

            if year_val is None:
                return None, None

            if isinstance(year_val, str) and "Q" in year_val:
                # Format like "2024-Q1"
                parts = year_val.split("-Q")
                year = int(parts[0])
                quarter = int(parts[1]) if len(parts) > 1 else None
            else:
                year = int(year_val)
                quarter = int(quarter_val) if quarter_val is not None else None
            return year, quarter
        except (ValueError, TypeError, IndexError):
            return None, None

    def _store_balance_sheets(
        self,
        stock: Stock,
        data,
        period_type: PeriodType,
        years: int,
    ) -> int:
        """Store balance sheet data."""
        count = 0
        current_year = datetime.now().year

        for _, row in data.iterrows():
            row_dict = row.to_dict()

            # Get year/quarter from data
            year, quarter = self._parse_period(row_dict)

            if year is None or year < current_year - years:
                continue

            # Check if record already exists
            existing = self.db.query(BalanceSheet).filter(
                BalanceSheet.stock_id == stock.id,
                BalanceSheet.period_type == period_type,
                BalanceSheet.year == year,
                BalanceSheet.quarter == quarter,
            ).first()

            if existing:
                continue

            period = f"{year}" if quarter is None else f"{year}-Q{quarter}"

            balance_sheet = BalanceSheet(
                stock_id=stock.id,
                period_type=period_type,
                year=year,
                quarter=quarter,
                period=period,
                total_assets=self._get_column_value(row_dict, [
                    "TỔNG CỘNG TÀI SẢN (đồng)", "TOTAL ASSETS (Bn. VND)", "asset", "totalAssets"
                ]),
                current_assets=self._get_column_value(row_dict, [
                    "TÀI SẢN NGẮN HẠN (đồng)", "CURRENT ASSETS (Bn. VND)", "shortAsset", "currentAssets"
                ]),
                cash_and_equivalents=self._get_column_value(row_dict, [
                    "Tiền và tương đương tiền (đồng)", "Cash and cash equivalents (Bn. VND)", "cash"
                ]),
                short_term_investments=self._get_column_value(row_dict, [
                    "Giá trị thuần đầu tư ngắn hạn (đồng)", "Short-term investments (Bn. VND)", "shortInvest"
                ]),
                accounts_receivable=self._get_column_value(row_dict, [
                    "Các khoản phải thu ngắn hạn (đồng)", "Accounts receivable (Bn. VND)", "shortReceivable"
                ]),
                inventory=self._get_column_value(row_dict, [
                    "Hàng tồn kho ròng", "Hàng tồn kho, ròng (đồng)", "Net Inventories", "Inventories, Net (Bn. VND)", "inventory"
                ]),
                non_current_assets=self._get_column_value(row_dict, [
                    "TÀI SẢN DÀI HẠN (đồng)", "LONG-TERM ASSETS (Bn. VND)", "longAsset"
                ]),
                fixed_assets=self._get_column_value(row_dict, [
                    "Tài sản cố định (đồng)", "Fixed assets (Bn. VND)", "fixedAsset"
                ]),
                long_term_investments=self._get_column_value(row_dict, [
                    "Đầu tư dài hạn (đồng)", "Long-term investments (Bn. VND)", "longInvest"
                ]),
                total_liabilities=self._get_column_value(row_dict, [
                    "NỢ PHẢI TRẢ (đồng)", "LIABILITIES (Bn. VND)", "debt", "totalLiabilities"
                ]),
                current_liabilities=self._get_column_value(row_dict, [
                    "Nợ ngắn hạn (đồng)", "Current liabilities (Bn. VND)", "shortDebt"
                ]),
                short_term_debt=self._get_column_value(row_dict, [
                    "Vay và nợ thuê tài chính ngắn hạn (đồng)", "Short-term borrowings (Bn. VND)", "shortLoan"
                ]),
                accounts_payable=self._get_column_value(row_dict, [
                    "Người mua trả tiền trước ngắn hạn (đồng)", "Advances from customers (Bn. VND)", "shortPayable"
                ]),
                non_current_liabilities=self._get_column_value(row_dict, [
                    "Nợ dài hạn (đồng)", "Long-term liabilities (Bn. VND)", "longDebt"
                ]),
                long_term_debt=self._get_column_value(row_dict, [
                    "Vay và nợ thuê tài chính dài hạn (đồng)", "Long-term borrowings (Bn. VND)", "longLoan"
                ]),
                total_equity=self._get_column_value(row_dict, [
                    "VỐN CHỦ SỞ HỮU (đồng)", "OWNER'S EQUITY(Bn.VND)", "equity", "totalEquity"
                ]),
                share_capital=self._get_column_value(row_dict, [
                    "Vốn góp của chủ sở hữu (đồng)", "Paid-in capital (Bn. VND)", "capital"
                ]),
                retained_earnings=self._get_column_value(row_dict, [
                    "Lãi chưa phân phối (đồng)", "Undistributed earnings (Bn. VND)", "undistriProfitCurrentTerm"
                ]),
                minority_interest=self._get_column_value(row_dict, [
                    "LỢI ÍCH CỦA CỔ ĐÔNG THIỂU SỐ", "MINORITY INTERESTS", "minorShareHolderProfit"
                ]),
            )

            self.db.add(balance_sheet)
            count += 1

        self.db.commit()
        return count

    def _store_income_statements(
        self,
        stock: Stock,
        data,
        period_type: PeriodType,
        years: int,
    ) -> int:
        """Store income statement data."""
        count = 0
        current_year = datetime.now().year

        for _, row in data.iterrows():
            row_dict = row.to_dict()

            year, quarter = self._parse_period(row_dict)

            if year is None or year < current_year - years:
                continue

            existing = self.db.query(IncomeStatement).filter(
                IncomeStatement.stock_id == stock.id,
                IncomeStatement.period_type == period_type,
                IncomeStatement.year == year,
                IncomeStatement.quarter == quarter,
            ).first()

            if existing:
                continue

            period = f"{year}" if quarter is None else f"{year}-Q{quarter}"

            income_statement = IncomeStatement(
                stock_id=stock.id,
                period_type=period_type,
                year=year,
                quarter=quarter,
                period=period,
                revenue=self._get_column_value(row_dict, [
                    "Doanh thu thuần", "Doanh thu (đồng)", "Revenue (Bn. VND)", "Net Sales", "revenue"
                ]),
                cost_of_revenue=self._get_column_value(row_dict, [
                    "Giá vốn hàng bán", "Cost of Sales", "costOfGoodSold"
                ]),
                gross_profit=self._get_column_value(row_dict, [
                    "Lãi gộp", "Gross Profit", "grossProfit"
                ]),
                operating_expenses=self._get_column_value(row_dict, [
                    "Chi phí tài chính", "Financial Expenses", "operationExpense"
                ]),
                selling_expenses=self._get_column_value(row_dict, [
                    "Chi phí bán hàng", "Selling Expenses", "sellingExpense"
                ]),
                administrative_expenses=self._get_column_value(row_dict, [
                    "Chi phí quản lý DN", "General & Admin Expenses", "adminExpense"
                ]),
                operating_income=self._get_column_value(row_dict, [
                    "Lãi/Lỗ từ hoạt động kinh doanh", "Operating Profit/Loss", "operationProfit"
                ]),
                interest_expense=self._get_column_value(row_dict, [
                    "Chi phí tiền lãi vay", "Interest Expenses", "interestExpense"
                ]),
                interest_income=self._get_column_value(row_dict, [
                    "Thu nhập tài chính", "Financial Income", "interestIncome"
                ]),
                other_income=self._get_column_value(row_dict, [
                    "Thu nhập khác", "Other income", "otherIncome"
                ]),
                other_expenses=self._get_column_value(row_dict, [
                    "Thu nhập/Chi phí khác", "Lợi nhuận khác", "Other Income/Expenses", "otherExpense"
                ]),
                profit_before_tax=self._get_column_value(row_dict, [
                    "LN trước thuế", "Profit before tax", "preTaxProfit"
                ]),
                income_tax=self._get_column_value(row_dict, [
                    "Chi phí thuế TNDN hiện hành", "Business income tax - current", "taxExpense"
                ]),
                net_income=self._get_column_value(row_dict, [
                    "Lợi nhuận thuần", "Net Profit For the Year", "postTaxProfit"
                ]),
                net_income_attributable=self._get_column_value(row_dict, [
                    "Lợi nhuận sau thuế của Cổ đông công ty mẹ (đồng)", "Cổ đông của Công ty mẹ",
                    "Attributable to parent company", "Attribute to parent company (Bn. VND)", "shareHolderIncome"
                ]),
                eps=self._get_column_value(row_dict, ["eps", "EPS", "earningsPerShare"]),
            )

            self.db.add(income_statement)
            count += 1

        self.db.commit()
        return count

    def _store_cash_flow_statements(
        self,
        stock: Stock,
        data,
        period_type: PeriodType,
        years: int,
    ) -> int:
        """Store cash flow statement data."""
        count = 0
        current_year = datetime.now().year

        for _, row in data.iterrows():
            row_dict = row.to_dict()

            year, quarter = self._parse_period(row_dict)

            if year is None or year < current_year - years:
                continue

            existing = self.db.query(CashFlowStatement).filter(
                CashFlowStatement.stock_id == stock.id,
                CashFlowStatement.period_type == period_type,
                CashFlowStatement.year == year,
                CashFlowStatement.quarter == quarter,
            ).first()

            if existing:
                continue

            period = f"{year}" if quarter is None else f"{year}-Q{quarter}"

            cash_flow = CashFlowStatement(
                stock_id=stock.id,
                period_type=period_type,
                year=year,
                quarter=quarter,
                period=period,
                operating_cash_flow=self._get_column_value(row_dict, [
                    "Lưu chuyển tiền tệ ròng từ các hoạt động SXKD",
                    "Net cash inflows/outflows from operating activities", "fromSale"
                ]),
                net_income_cf=self._get_column_value(row_dict, [
                    "Lãi/Lỗ ròng trước thuế", "Net Profit/Loss before tax", "fromProfit"
                ]),
                depreciation=self._get_column_value(row_dict, [
                    "Khấu hao TSCĐ", "Depreciation and Amortisation", "depreciation"
                ]),
                changes_in_working_capital=self._get_column_value(row_dict, [
                    "Lưu chuyển tiền thuần từ HĐKD trước thay đổi VLĐ",
                    "Operating profit before changes in working capital", "changeInWorkingCapital"
                ]),
                investing_cash_flow=self._get_column_value(row_dict, [
                    "Lưu chuyển từ hoạt động đầu tư",
                    "Net Cash Flows from Investing Activities", "fromInvest"
                ]),
                capital_expenditure=self._get_column_value(row_dict, [
                    "Mua sắm TSCĐ", "Purchase of fixed assets", "purchaseFixedAsset"
                ]),
                investments_purchases=self._get_column_value(row_dict, [
                    "Tiền chi cho vay, mua công cụ nợ của đơn vị khác (đồng)",
                    "Đầu tư vào các doanh nghiệp khác",
                    "Investment in other entities", "Loans granted, purchases of debt instruments (Bn. VND)"
                ]),
                investments_sales=self._get_column_value(row_dict, [
                    "Tiền thu từ việc bán các khoản đầu tư vào doanh nghiệp khác",
                    "Tiền thu hồi cho vay, bán lại các công cụ nợ của đơn vị khác (đồng)",
                    "Proceeds from divestment in other entities", "investmentSales"
                ]),
                financing_cash_flow=self._get_column_value(row_dict, [
                    "Lưu chuyển tiền từ hoạt động tài chính",
                    "Cash flows from financial activities", "fromFinancial"
                ]),
                debt_issued=self._get_column_value(row_dict, [
                    "Tiền thu được các khoản đi vay", "Proceeds from borrowings", "receiveInvestment"
                ]),
                debt_repaid=self._get_column_value(row_dict, [
                    "Tiền trả các khoản đi vay", "Repayment of borrowings", "paybackDebt"
                ]),
                dividends_paid=self._get_column_value(row_dict, [
                    "Cổ tức đã trả", "Dividends paid", "dividendsPaid"
                ]),
                stock_issued=self._get_column_value(row_dict, [
                    "Tăng vốn cổ phần từ góp vốn và/hoặc phát hành cổ phiếu",
                    "Increase in charter captial", "stockIssued"
                ]),
                stock_repurchased=self._get_column_value(row_dict, [
                    "Chi trả cho việc mua lại, trả cổ phiếu",
                    "Payments for share repurchases", "stockRepurchased"
                ]),
                net_change_in_cash=self._get_column_value(row_dict, [
                    "Lưu chuyển tiền thuần trong kỳ",
                    "Net increase/decrease in cash and cash equivalents", "freeCashFlow"
                ]),
                beginning_cash=self._get_column_value(row_dict, [
                    "Tiền và tương đương tiền", "Cash and cash equivalents", "beginningCash"
                ]),
                ending_cash=self._get_column_value(row_dict, [
                    "Tiền và tương đương tiền cuối kỳ",
                    "Cash and Cash Equivalents at the end of period", "endingCash"
                ]),
            )

            self.db.add(cash_flow)
            count += 1

        self.db.commit()
        return count

    def search_stocks(self, query: str, limit: int = 20) -> List[Dict[str, str]]:
        """
        Search for stocks by symbol or name.
        Pattern: Cache -> Database -> API (with backfill)
        """
        query_upper = query.upper().strip()
        if not query_upper:
            return []

        # 1. Check cache first
        cache_key = query_upper
        cached = _search_cache.get(cache_key)
        if cached and (time.time() - cached["timestamp"]) < CACHE_TTL:
            logger.debug(f"Search cache hit for: {query_upper}")
            return cached["results"][:limit]

        results = []
        seen_symbols = set()

        # 2. Search from database
        db_results = self._search_from_db(query_upper, limit)
        for item in db_results:
            if item["symbol"] not in seen_symbols:
                results.append(item)
                seen_symbols.add(item["symbol"])

        # 3. If not enough results, search from API and backfill
        if len(results) < limit:
            api_results = self._search_from_api(query_upper, limit * 2)
            for item in api_results:
                if item["symbol"] not in seen_symbols:
                    results.append(item)
                    seen_symbols.add(item["symbol"])
                    # Backfill to database
                    self._backfill_stock(item)
                    if len(results) >= limit:
                        break

        # 4. Update cache
        _search_cache[cache_key] = {
            "results": results,
            "timestamp": time.time(),
        }

        return results[:limit]

    def _search_from_db(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Search stocks from database."""
        try:
            # Search by symbol (exact match first, then contains)
            stocks = self.db.query(Stock).filter(
                (Stock.symbol.ilike(f"{query}%")) |
                (Stock.symbol.ilike(f"%{query}%")) |
                (Stock.name.ilike(f"%{query}%"))
            ).order_by(
                # Prioritize exact symbol match
                Stock.symbol.ilike(f"{query}%").desc(),
                Stock.symbol
            ).limit(limit).all()

            return [
                {
                    "symbol": stock.symbol,
                    "organName": stock.name or "",
                    "exchange": stock.exchange or "",
                }
                for stock in stocks
            ]
        except Exception as e:
            logger.warning(f"DB search failed: {e}")
            return []

    def _search_from_api(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Search stocks from vnstock API with caching of all symbols."""
        try:
            # Check if we have cached all symbols
            if _all_symbols_cache["data"] is None or (time.time() - _all_symbols_cache["timestamp"]) > CACHE_TTL:
                logger.debug("Fetching all symbols from API")
                vs = Vnstock().stock(symbol="VNM", source="VCI")
                listing = vs.listing.all_symbols()
                if listing is not None and not listing.empty:
                    _all_symbols_cache["data"] = listing
                    _all_symbols_cache["timestamp"] = time.time()
                else:
                    return []

            listing = _all_symbols_cache["data"]
            if listing is None:
                return []

            # Filter by query
            symbol_col = "symbol"
            name_col = "organ_name"

            mask = listing[symbol_col].astype(str).str.upper().str.contains(query, na=False)
            if name_col in listing.columns:
                mask = mask | listing[name_col].astype(str).str.upper().str.contains(query, na=False)

            results = listing[mask].head(limit)

            output = []
            for _, row in results.iterrows():
                output.append({
                    "symbol": str(row.get(symbol_col, "")),
                    "organName": str(row.get(name_col, "")),
                    "exchange": str(row.get("exchange", "")),
                })
            return output
        except Exception as e:
            logger.warning(f"API search failed: {e}")
            return []

    def _backfill_stock(self, stock_data: Dict[str, str]) -> None:
        """Backfill stock to database if not exists."""
        try:
            symbol = stock_data["symbol"].upper()
            existing = self.db.query(Stock).filter(Stock.symbol == symbol).first()
            if not existing:
                stock = Stock(
                    symbol=symbol,
                    name=stock_data.get("organName"),
                    exchange=stock_data.get("exchange"),
                )
                self.db.add(stock)
                self.db.commit()
                logger.debug(f"Backfilled stock: {symbol}")
        except Exception as e:
            logger.warning(f"Failed to backfill stock {stock_data.get('symbol')}: {e}")
            self.db.rollback()
