"""PDF scraper service for fetching financial data from Vietnamese stock PDFs with OCR support."""

import httpx
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
from io import BytesIO
from sqlalchemy.orm import Session

from ..models.financial import (
    Stock,
    BalanceSheet,
    IncomeStatement,
    CashFlowStatement,
    PeriodType,
)

logger = logging.getLogger(__name__)

# Optional imports for PDF parsing
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not installed - PDF text extraction disabled")

# Optional imports for OCR
try:
    import pdf2image
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    logger.warning("OCR dependencies not installed (pdf2image, pytesseract) - OCR disabled")


class PDFScraper:
    """Service for fetching financial data from Vietnamese stock PDFs with OCR support."""

    # PDF source API endpoint (CafeF)
    PDF_API_URL = "https://cafef.vn/du-lieu/Ajax/PageNew/FileBCTC.ashx"

    TIMEOUT = 60.0
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/html,application/xhtml+xml",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    # Field mappings for balance sheet (Vietnamese to DB fields)
    BALANCE_SHEET_PATTERNS = {
        r"tài sản ngắn hạn.*?(\d[\d.,]+)": "current_assets",
        r"tiền và.*?tương đương tiền.*?(\d[\d.,]+)": "cash_and_equivalents",
        r"đầu tư.*?ngắn hạn.*?(\d[\d.,]+)": "short_term_investments",
        r"phải thu.*?ngắn hạn.*?(\d[\d.,]+)": "accounts_receivable",
        r"hàng tồn kho.*?(\d[\d.,]+)": "inventory",
        r"tài sản dài hạn.*?(\d[\d.,]+)": "non_current_assets",
        r"tài sản cố định.*?(\d[\d.,]+)": "fixed_assets",
        r"đầu tư.*?dài hạn.*?(\d[\d.,]+)": "long_term_investments",
        r"tổng.*?tài sản.*?(\d[\d.,]+)": "total_assets",
        r"nợ phải trả.*?(\d[\d.,]+)": "total_liabilities",
        r"nợ ngắn hạn.*?(\d[\d.,]+)": "current_liabilities",
        r"vay.*?ngắn hạn.*?(\d[\d.,]+)": "short_term_debt",
        r"phải trả người bán.*?(\d[\d.,]+)": "accounts_payable",
        r"nợ dài hạn.*?(\d[\d.,]+)": "non_current_liabilities",
        r"vay.*?dài hạn.*?(\d[\d.,]+)": "long_term_debt",
        r"vốn chủ sở hữu.*?(\d[\d.,]+)": "total_equity",
        r"vốn góp.*?(\d[\d.,]+)": "share_capital",
        r"lợi nhuận.*?chưa phân phối.*?(\d[\d.,]+)": "retained_earnings",
        r"lợi ích.*?cổ đông.*?thiểu số.*?(\d[\d.,]+)": "minority_interest",
    }

    INCOME_STATEMENT_PATTERNS = {
        r"doanh thu.*?bán hàng.*?(\d[\d.,]+)": "revenue",
        r"giá vốn.*?hàng bán.*?(\d[\d.,]+)": "cost_of_revenue",
        r"lợi nhuận gộp.*?(\d[\d.,]+)": "gross_profit",
        r"chi phí.*?bán hàng.*?(\d[\d.,]+)": "selling_expenses",
        r"chi phí.*?quản lý.*?(\d[\d.,]+)": "administrative_expenses",
        r"lợi nhuận.*?hoạt động.*?kinh doanh.*?(\d[\d.,]+)": "operating_income",
        r"doanh thu.*?tài chính.*?(\d[\d.,]+)": "interest_income",
        r"chi phí.*?lãi vay.*?(\d[\d.,]+)": "interest_expense",
        r"thu nhập khác.*?(\d[\d.,]+)": "other_income",
        r"chi phí khác.*?(\d[\d.,]+)": "other_expenses",
        r"lợi nhuận.*?trước thuế.*?(\d[\d.,]+)": "profit_before_tax",
        r"chi phí.*?thuế.*?tndn.*?(\d[\d.,]+)": "income_tax",
        r"lợi nhuận.*?sau thuế.*?(\d[\d.,]+)": "net_income",
    }

    CASH_FLOW_PATTERNS = {
        r"lưu chuyển tiền.*?hoạt động.*?kinh doanh.*?(\d[\d.,]+)": "operating_cash_flow",
        r"khấu hao.*?(\d[\d.,]+)": "depreciation",
        r"lưu chuyển tiền.*?hoạt động.*?đầu tư.*?(\d[\d.,]+)": "investing_cash_flow",
        r"mua sắm.*?tscđ.*?(\d[\d.,]+)": "capital_expenditure",
        r"lưu chuyển tiền.*?hoạt động.*?tài chính.*?(\d[\d.,]+)": "financing_cash_flow",
        r"tiền thu.*?đi vay.*?(\d[\d.,]+)": "debt_issued",
        r"tiền trả.*?nợ.*?vay.*?(\d[\d.,]+)": "debt_repaid",
        r"cổ tức.*?đã trả.*?(\d[\d.,]+)": "dividends_paid",
        r"tiền.*?đầu kỳ.*?(\d[\d.,]+)": "beginning_cash",
        r"tiền.*?cuối kỳ.*?(\d[\d.,]+)": "ending_cash",
    }

    def __init__(self, db: Session):
        self.db = db
        self.client = httpx.Client(headers=self.HEADERS, timeout=self.TIMEOUT, follow_redirects=True)

    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()

    def get_or_create_stock(self, symbol: str) -> Stock:
        """Get existing stock or create a new one."""
        symbol = symbol.upper()
        stock = self.db.query(Stock).filter(Stock.symbol == symbol).first()

        if not stock:
            stock = Stock(symbol=symbol)
            self.db.add(stock)
            self.db.commit()
            self.db.refresh(stock)

        return stock

    def fetch_pdf_links(self, symbol: str) -> List[Dict]:
        """Fetch PDF links from source API."""
        url = f"{self.PDF_API_URL}?Symbol={symbol.upper()}"

        try:
            response = self.client.get(url)
            response.raise_for_status()
            data = response.json()

            # API returns {"Data": [...], "Message": ..., "Success": ...}
            items = data.get("Data", []) if isinstance(data, dict) else data

            pdf_links = []
            for item in items:
                name = item.get("Name", "")
                # Filter for consolidated reports (hợp nhất)
                if "hợp nhất" in name.lower():
                    pdf_links.append({
                        "year": item.get("Year"),
                        "quarter": item.get("Quarter"),
                        "name": name,
                        "link": item.get("Link"),
                    })

            logger.info(f"Found {len(pdf_links)} consolidated PDF reports for {symbol}")
            return pdf_links

        except Exception as e:
            logger.error(f"Failed to fetch PDF links for {symbol}: {e}")
            return []

    def fetch_financial_reports(
        self,
        symbol: str,
        period_type: str = "annual",
        years: int = 6,
    ) -> Dict[str, Any]:
        """Fetch all financial reports from PDFs using OCR."""
        if not HAS_PDFPLUMBER and not HAS_OCR:
            logger.error("No PDF parsing libraries available")
            return self._empty_result(symbol)

        symbol = symbol.upper()
        stock = self.get_or_create_stock(symbol)
        period_enum = PeriodType.ANNUAL if period_type == "annual" else PeriodType.QUARTER
        current_year = datetime.now().year

        # Fetch PDF links
        pdf_links = self.fetch_pdf_links(symbol)

        if not pdf_links:
            logger.warning(f"No PDF links found for {symbol}")
            return self._empty_result(symbol, stock)

        balance_sheets_added = 0
        income_statements_added = 0
        cash_flow_statements_added = 0

        for pdf_info in pdf_links:
            year = pdf_info.get("year")
            quarter = pdf_info.get("quarter")

            if not year or year < current_year - years:
                continue

            # Filter by period type (Quarter 0 or 5 = annual report)
            is_annual = quarter in [0, 5, None]
            if period_type == "annual" and not is_annual:
                continue
            if period_type == "quarter" and is_annual:
                continue

            pdf_url = pdf_info.get("link")
            if not pdf_url:
                continue

            logger.info(f"Processing PDF: {pdf_info.get('name', '')[:50]}... Year={year} Q={quarter}")

            try:
                # Download PDF
                pdf_data = self._download_pdf(pdf_url)
                if not pdf_data:
                    continue

                # Parse PDF (try pdfplumber first, then OCR)
                parsed = self._parse_pdf(pdf_data)

                if not any(parsed.values()):
                    logger.warning(f"No data extracted from PDF for {symbol} {year}-Q{quarter}")
                    continue

                # Store the parsed data
                period = f"{year}" if is_annual else f"{year}-Q{quarter}"
                actual_quarter = None if is_annual else quarter

                if parsed.get("balance_sheet"):
                    added = self._store_balance_sheet(
                        stock, parsed["balance_sheet"],
                        period_enum, year, actual_quarter, period
                    )
                    balance_sheets_added += added

                if parsed.get("income_statement"):
                    added = self._store_income_statement(
                        stock, parsed["income_statement"],
                        period_enum, year, actual_quarter, period
                    )
                    income_statements_added += added

                if parsed.get("cash_flow"):
                    added = self._store_cash_flow(
                        stock, parsed["cash_flow"],
                        period_enum, year, actual_quarter, period
                    )
                    cash_flow_statements_added += added

            except Exception as e:
                logger.warning(f"Failed to parse PDF {pdf_url}: {e}")
                continue

        logger.info(f"PDF scrape complete for {symbol}: BS={balance_sheets_added}, IS={income_statements_added}, CF={cash_flow_statements_added}")

        return {
            "stock": stock,
            "balance_sheets_count": balance_sheets_added,
            "income_statements_count": income_statements_added,
            "cash_flow_statements_count": cash_flow_statements_added,
        }

    def _empty_result(self, symbol: str, stock: Stock = None) -> Dict[str, Any]:
        """Return empty result."""
        if stock is None:
            stock = self.get_or_create_stock(symbol)
        return {
            "stock": stock,
            "balance_sheets_count": 0,
            "income_statements_count": 0,
            "cash_flow_statements_count": 0,
        }

    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download PDF from URL."""
        try:
            response = self.client.get(url)
            response.raise_for_status()
            logger.debug(f"Downloaded PDF: {len(response.content) / 1024:.1f} KB")
            return response.content
        except Exception as e:
            logger.error(f"Failed to download PDF from {url}: {e}")
            return None

    def _parse_pdf(self, pdf_data: bytes) -> Dict[str, Dict]:
        """Parse financial data from PDF using pdfplumber or OCR."""
        result = {
            "balance_sheet": {},
            "income_statement": {},
            "cash_flow": {},
        }

        text = ""

        # Try pdfplumber first (for text-based PDFs)
        if HAS_PDFPLUMBER:
            text = self._extract_text_pdfplumber(pdf_data)

        # If no text extracted, try OCR
        if len(text) < 1000 and HAS_OCR:
            logger.info("PDF appears to be image-based, using OCR...")
            text = self._extract_text_ocr(pdf_data)

        if not text:
            logger.warning("Could not extract text from PDF")
            return result

        # Parse financial data from text
        result["balance_sheet"] = self._parse_balance_sheet(text)
        result["income_statement"] = self._parse_income_statement(text)
        result["cash_flow"] = self._parse_cash_flow(text)

        return result

    def _extract_text_pdfplumber(self, pdf_data: bytes) -> str:
        """Extract text using pdfplumber."""
        try:
            all_text = []
            with pdfplumber.open(BytesIO(pdf_data)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    all_text.append(text)
            return "\n".join(all_text)
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            return ""

    def _extract_text_ocr(self, pdf_data: bytes, max_pages: int = 15) -> str:
        """Extract text using OCR (for image-based PDFs)."""
        try:
            # Convert PDF to images
            images = pdf2image.convert_from_bytes(
                pdf_data,
                first_page=1,
                last_page=max_pages,
                dpi=200
            )

            logger.info(f"OCR: Processing {len(images)} pages...")

            all_text = []
            for i, image in enumerate(images):
                # OCR with Vietnamese + English
                text = pytesseract.image_to_string(
                    image,
                    lang='vie+eng',
                    config='--psm 6'
                )
                all_text.append(text)

                # Log progress for large PDFs
                if (i + 1) % 5 == 0:
                    logger.debug(f"OCR progress: {i + 1}/{len(images)} pages")

            return "\n".join(all_text)

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return ""

    def _parse_balance_sheet(self, text: str) -> Dict[str, float]:
        """Extract balance sheet data from text."""
        return self._extract_values(text, self.BALANCE_SHEET_PATTERNS)

    def _parse_income_statement(self, text: str) -> Dict[str, float]:
        """Extract income statement data from text."""
        return self._extract_values(text, self.INCOME_STATEMENT_PATTERNS)

    def _parse_cash_flow(self, text: str) -> Dict[str, float]:
        """Extract cash flow data from text."""
        return self._extract_values(text, self.CASH_FLOW_PATTERNS)

    def _extract_values(self, text: str, patterns: Dict[str, str]) -> Dict[str, float]:
        """Extract financial values using regex patterns."""
        result = {}
        text_lower = text.lower()

        for pattern, field in patterns.items():
            matches = re.findall(pattern, text_lower, re.IGNORECASE | re.DOTALL)
            if matches:
                # Get the first match and parse number
                value = self._parse_number(matches[0])
                if value is not None and value > 0:
                    result[field] = value

        return result

    def _parse_number(self, text: str) -> Optional[float]:
        """Parse a number from text (handles Vietnamese format)."""
        if not text:
            return None

        text = str(text).strip().replace(' ', '')

        # Remove thousand separators and handle decimal
        # Vietnamese: 1.234.567,89 or 1,234,567.89
        if ',' in text and '.' in text:
            if text.rfind(',') > text.rfind('.'):
                # Vietnamese format: 1.234,56
                text = text.replace('.', '').replace(',', '.')
            else:
                # English format: 1,234.56
                text = text.replace(',', '')
        elif ',' in text:
            parts = text.split(',')
            if len(parts) == 2 and len(parts[1]) <= 2:
                text = text.replace(',', '.')
            else:
                text = text.replace(',', '')
        elif text.count('.') > 1:
            # Multiple dots as thousand separators
            text = text.replace('.', '')

        try:
            return float(text)
        except ValueError:
            return None

    def _store_balance_sheet(
        self, stock: Stock, data: Dict,
        period_type: PeriodType, year: int, quarter: Optional[int], period: str
    ) -> int:
        """Store balance sheet data."""
        if not data:
            return 0

        # Check if exists
        existing = self.db.query(BalanceSheet).filter(
            BalanceSheet.stock_id == stock.id,
            BalanceSheet.period_type == period_type,
            BalanceSheet.year == year,
            BalanceSheet.quarter == quarter,
        ).first()

        if existing:
            return 0

        balance_sheet = BalanceSheet(
            stock_id=stock.id,
            period_type=period_type,
            year=year,
            quarter=quarter,
            period=period,
            total_assets=data.get('total_assets'),
            current_assets=data.get('current_assets'),
            cash_and_equivalents=data.get('cash_and_equivalents'),
            short_term_investments=data.get('short_term_investments'),
            accounts_receivable=data.get('accounts_receivable'),
            inventory=data.get('inventory'),
            non_current_assets=data.get('non_current_assets'),
            fixed_assets=data.get('fixed_assets'),
            long_term_investments=data.get('long_term_investments'),
            total_liabilities=data.get('total_liabilities'),
            current_liabilities=data.get('current_liabilities'),
            short_term_debt=data.get('short_term_debt'),
            accounts_payable=data.get('accounts_payable'),
            non_current_liabilities=data.get('non_current_liabilities'),
            long_term_debt=data.get('long_term_debt'),
            total_equity=data.get('total_equity'),
            share_capital=data.get('share_capital'),
            retained_earnings=data.get('retained_earnings'),
            minority_interest=data.get('minority_interest'),
        )

        self.db.add(balance_sheet)
        self.db.commit()
        return 1

    def _store_income_statement(
        self, stock: Stock, data: Dict,
        period_type: PeriodType, year: int, quarter: Optional[int], period: str
    ) -> int:
        """Store income statement data."""
        if not data:
            return 0

        existing = self.db.query(IncomeStatement).filter(
            IncomeStatement.stock_id == stock.id,
            IncomeStatement.period_type == period_type,
            IncomeStatement.year == year,
            IncomeStatement.quarter == quarter,
        ).first()

        if existing:
            return 0

        income_statement = IncomeStatement(
            stock_id=stock.id,
            period_type=period_type,
            year=year,
            quarter=quarter,
            period=period,
            revenue=data.get('revenue'),
            cost_of_revenue=data.get('cost_of_revenue'),
            gross_profit=data.get('gross_profit'),
            operating_expenses=data.get('operating_expenses'),
            selling_expenses=data.get('selling_expenses'),
            administrative_expenses=data.get('administrative_expenses'),
            operating_income=data.get('operating_income'),
            interest_expense=data.get('interest_expense'),
            interest_income=data.get('interest_income'),
            other_income=data.get('other_income'),
            other_expenses=data.get('other_expenses'),
            profit_before_tax=data.get('profit_before_tax'),
            income_tax=data.get('income_tax'),
            net_income=data.get('net_income'),
            net_income_attributable=data.get('net_income_attributable'),
            eps=data.get('eps'),
        )

        self.db.add(income_statement)
        self.db.commit()
        return 1

    def _store_cash_flow(
        self, stock: Stock, data: Dict,
        period_type: PeriodType, year: int, quarter: Optional[int], period: str
    ) -> int:
        """Store cash flow statement data."""
        if not data:
            return 0

        existing = self.db.query(CashFlowStatement).filter(
            CashFlowStatement.stock_id == stock.id,
            CashFlowStatement.period_type == period_type,
            CashFlowStatement.year == year,
            CashFlowStatement.quarter == quarter,
        ).first()

        if existing:
            return 0

        cash_flow = CashFlowStatement(
            stock_id=stock.id,
            period_type=period_type,
            year=year,
            quarter=quarter,
            period=period,
            operating_cash_flow=data.get('operating_cash_flow'),
            net_income_cf=data.get('net_income_cf'),
            depreciation=data.get('depreciation'),
            changes_in_working_capital=data.get('changes_in_working_capital'),
            investing_cash_flow=data.get('investing_cash_flow'),
            capital_expenditure=data.get('capital_expenditure'),
            investments_purchases=data.get('investments_purchases'),
            investments_sales=data.get('investments_sales'),
            financing_cash_flow=data.get('financing_cash_flow'),
            debt_issued=data.get('debt_issued'),
            debt_repaid=data.get('debt_repaid'),
            dividends_paid=data.get('dividends_paid'),
            stock_issued=data.get('stock_issued'),
            stock_repurchased=data.get('stock_repurchased'),
            net_change_in_cash=data.get('net_change_in_cash'),
            beginning_cash=data.get('beginning_cash'),
            ending_cash=data.get('ending_cash'),
        )

        self.db.add(cash_flow)
        self.db.commit()
        return 1
