from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum


class PeriodType(str, Enum):
    """Period type for financial reports."""
    ANNUAL = "annual"
    QUARTER = "quarter"


# Stock schemas
class StockBase(BaseModel):
    """Base stock schema."""
    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None


class StockCreate(StockBase):
    """Schema for creating a stock."""
    pass


class StockResponse(StockBase):
    """Schema for stock response."""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Balance Sheet schemas
class BalanceSheetBase(BaseModel):
    """Base balance sheet schema."""
    period_type: PeriodType
    year: int
    quarter: Optional[int] = None
    period: str

    # Assets
    total_assets: Optional[float] = None
    current_assets: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    short_term_investments: Optional[float] = None
    accounts_receivable: Optional[float] = None
    inventory: Optional[float] = None
    non_current_assets: Optional[float] = None
    fixed_assets: Optional[float] = None
    long_term_investments: Optional[float] = None

    # Liabilities
    total_liabilities: Optional[float] = None
    current_liabilities: Optional[float] = None
    short_term_debt: Optional[float] = None
    accounts_payable: Optional[float] = None
    non_current_liabilities: Optional[float] = None
    long_term_debt: Optional[float] = None

    # Equity
    total_equity: Optional[float] = None
    share_capital: Optional[float] = None
    retained_earnings: Optional[float] = None
    minority_interest: Optional[float] = None


class BalanceSheetResponse(BalanceSheetBase):
    """Schema for balance sheet response."""
    id: int
    stock_id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Income Statement schemas
class IncomeStatementBase(BaseModel):
    """Base income statement schema."""
    period_type: PeriodType
    year: int
    quarter: Optional[int] = None
    period: str

    # Revenue
    revenue: Optional[float] = None
    cost_of_revenue: Optional[float] = None
    gross_profit: Optional[float] = None

    # Operating
    operating_expenses: Optional[float] = None
    selling_expenses: Optional[float] = None
    administrative_expenses: Optional[float] = None
    operating_income: Optional[float] = None

    # Other
    interest_expense: Optional[float] = None
    interest_income: Optional[float] = None
    other_income: Optional[float] = None
    other_expenses: Optional[float] = None

    # Profit
    profit_before_tax: Optional[float] = None
    income_tax: Optional[float] = None
    net_income: Optional[float] = None
    net_income_attributable: Optional[float] = None
    eps: Optional[float] = None


class IncomeStatementResponse(IncomeStatementBase):
    """Schema for income statement response."""
    id: int
    stock_id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Cash Flow Statement schemas
class CashFlowStatementBase(BaseModel):
    """Base cash flow statement schema."""
    period_type: PeriodType
    year: int
    quarter: Optional[int] = None
    period: str

    # Operating activities
    operating_cash_flow: Optional[float] = None
    net_income_cf: Optional[float] = None
    depreciation: Optional[float] = None
    changes_in_working_capital: Optional[float] = None

    # Investing activities
    investing_cash_flow: Optional[float] = None
    capital_expenditure: Optional[float] = None
    investments_purchases: Optional[float] = None
    investments_sales: Optional[float] = None

    # Financing activities
    financing_cash_flow: Optional[float] = None
    debt_issued: Optional[float] = None
    debt_repaid: Optional[float] = None
    dividends_paid: Optional[float] = None
    stock_issued: Optional[float] = None
    stock_repurchased: Optional[float] = None

    # Net change
    net_change_in_cash: Optional[float] = None
    beginning_cash: Optional[float] = None
    ending_cash: Optional[float] = None


class CashFlowStatementResponse(CashFlowStatementBase):
    """Schema for cash flow statement response."""
    id: int
    stock_id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Combined report response
class FinancialReportResponse(BaseModel):
    """Combined financial report response."""
    stock: StockResponse
    balance_sheets: List[BalanceSheetResponse] = []
    income_statements: List[IncomeStatementResponse] = []
    cash_flow_statements: List[CashFlowStatementResponse] = []


# Request schemas
class FetchDataRequest(BaseModel):
    """Request to fetch data from vnstock3."""
    period_type: PeriodType = PeriodType.ANNUAL
    years: int = 5  # Number of years to fetch


class FetchDataResponse(BaseModel):
    """Response after fetching data."""
    message: str
    stock: StockResponse
    balance_sheets_count: int
    income_statements_count: int
    cash_flow_statements_count: int
