from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..database import Base


class PeriodType(str, enum.Enum):
    """Period type for financial reports."""
    ANNUAL = "annual"
    QUARTER = "quarter"


class Stock(Base):
    """Stock symbols and information."""
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    exchange = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    balance_sheets = relationship("BalanceSheet", back_populates="stock", cascade="all, delete-orphan")
    income_statements = relationship("IncomeStatement", back_populates="stock", cascade="all, delete-orphan")
    cash_flow_statements = relationship("CashFlowStatement", back_populates="stock", cascade="all, delete-orphan")


class BalanceSheet(Base):
    """Balance sheet financial data."""
    __tablename__ = "balance_sheets"

    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    period_type = Column(Enum(PeriodType), nullable=False)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=True)  # 1-4 for quarterly, null for annual
    period = Column(String(20), nullable=False)  # e.g., "2024" or "2024-Q1"

    # Assets
    total_assets = Column(Numeric(20, 4), nullable=True)
    current_assets = Column(Numeric(20, 4), nullable=True)
    cash_and_equivalents = Column(Numeric(20, 4), nullable=True)
    short_term_investments = Column(Numeric(20, 4), nullable=True)
    accounts_receivable = Column(Numeric(20, 4), nullable=True)
    inventory = Column(Numeric(20, 4), nullable=True)
    non_current_assets = Column(Numeric(20, 4), nullable=True)
    fixed_assets = Column(Numeric(20, 4), nullable=True)
    long_term_investments = Column(Numeric(20, 4), nullable=True)

    # Liabilities
    total_liabilities = Column(Numeric(20, 4), nullable=True)
    current_liabilities = Column(Numeric(20, 4), nullable=True)
    short_term_debt = Column(Numeric(20, 4), nullable=True)
    accounts_payable = Column(Numeric(20, 4), nullable=True)
    non_current_liabilities = Column(Numeric(20, 4), nullable=True)
    long_term_debt = Column(Numeric(20, 4), nullable=True)

    # Equity
    total_equity = Column(Numeric(20, 4), nullable=True)
    share_capital = Column(Numeric(20, 4), nullable=True)
    retained_earnings = Column(Numeric(20, 4), nullable=True)
    minority_interest = Column(Numeric(20, 4), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    stock = relationship("Stock", back_populates="balance_sheets")

    __table_args__ = (
        UniqueConstraint('stock_id', 'period_type', 'year', 'quarter', name='uq_balance_sheet_period'),
    )


class IncomeStatement(Base):
    """Income statement financial data."""
    __tablename__ = "income_statements"

    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    period_type = Column(Enum(PeriodType), nullable=False)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=True)
    period = Column(String(20), nullable=False)

    # Revenue
    revenue = Column(Numeric(20, 4), nullable=True)
    cost_of_revenue = Column(Numeric(20, 4), nullable=True)
    gross_profit = Column(Numeric(20, 4), nullable=True)

    # Operating
    operating_expenses = Column(Numeric(20, 4), nullable=True)
    selling_expenses = Column(Numeric(20, 4), nullable=True)
    administrative_expenses = Column(Numeric(20, 4), nullable=True)
    operating_income = Column(Numeric(20, 4), nullable=True)

    # Other income/expenses
    interest_expense = Column(Numeric(20, 4), nullable=True)
    interest_income = Column(Numeric(20, 4), nullable=True)
    other_income = Column(Numeric(20, 4), nullable=True)
    other_expenses = Column(Numeric(20, 4), nullable=True)

    # Profit
    profit_before_tax = Column(Numeric(20, 4), nullable=True)
    income_tax = Column(Numeric(20, 4), nullable=True)
    net_income = Column(Numeric(20, 4), nullable=True)
    net_income_attributable = Column(Numeric(20, 4), nullable=True)  # Attributable to parent company

    # Per share
    eps = Column(Numeric(20, 4), nullable=True)  # Earnings per share

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    stock = relationship("Stock", back_populates="income_statements")

    __table_args__ = (
        UniqueConstraint('stock_id', 'period_type', 'year', 'quarter', name='uq_income_statement_period'),
    )


class CashFlowStatement(Base):
    """Cash flow statement financial data."""
    __tablename__ = "cash_flow_statements"

    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    period_type = Column(Enum(PeriodType), nullable=False)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=True)
    period = Column(String(20), nullable=False)

    # Operating activities
    operating_cash_flow = Column(Numeric(20, 4), nullable=True)
    net_income_cf = Column(Numeric(20, 4), nullable=True)
    depreciation = Column(Numeric(20, 4), nullable=True)
    changes_in_working_capital = Column(Numeric(20, 4), nullable=True)

    # Investing activities
    investing_cash_flow = Column(Numeric(20, 4), nullable=True)
    capital_expenditure = Column(Numeric(20, 4), nullable=True)
    investments_purchases = Column(Numeric(20, 4), nullable=True)
    investments_sales = Column(Numeric(20, 4), nullable=True)

    # Financing activities
    financing_cash_flow = Column(Numeric(20, 4), nullable=True)
    debt_issued = Column(Numeric(20, 4), nullable=True)
    debt_repaid = Column(Numeric(20, 4), nullable=True)
    dividends_paid = Column(Numeric(20, 4), nullable=True)
    stock_issued = Column(Numeric(20, 4), nullable=True)
    stock_repurchased = Column(Numeric(20, 4), nullable=True)

    # Net change
    net_change_in_cash = Column(Numeric(20, 4), nullable=True)
    beginning_cash = Column(Numeric(20, 4), nullable=True)
    ending_cash = Column(Numeric(20, 4), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    stock = relationship("Stock", back_populates="cash_flow_statements")

    __table_args__ = (
        UniqueConstraint('stock_id', 'period_type', 'year', 'quarter', name='uq_cash_flow_period'),
    )
