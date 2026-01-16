export type PeriodType = 'annual' | 'quarter';

export interface Stock {
  id: number;
  symbol: string;
  name: string | null;
  exchange: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface StockSearchResult {
  symbol: string;
  organName: string;
  exchange?: string;
}

export interface BalanceSheet {
  id: number;
  stock_id: number;
  period_type: PeriodType;
  year: number;
  quarter: number | null;
  period: string;

  // Assets
  total_assets: number | null;
  current_assets: number | null;
  cash_and_equivalents: number | null;
  short_term_investments: number | null;
  accounts_receivable: number | null;
  inventory: number | null;
  non_current_assets: number | null;
  fixed_assets: number | null;
  long_term_investments: number | null;

  // Liabilities
  total_liabilities: number | null;
  current_liabilities: number | null;
  short_term_debt: number | null;
  accounts_payable: number | null;
  non_current_liabilities: number | null;
  long_term_debt: number | null;

  // Equity
  total_equity: number | null;
  share_capital: number | null;
  retained_earnings: number | null;
  minority_interest: number | null;

  created_at: string | null;
}

export interface IncomeStatement {
  id: number;
  stock_id: number;
  period_type: PeriodType;
  year: number;
  quarter: number | null;
  period: string;

  // Revenue
  revenue: number | null;
  cost_of_revenue: number | null;
  gross_profit: number | null;

  // Operating
  operating_expenses: number | null;
  selling_expenses: number | null;
  administrative_expenses: number | null;
  operating_income: number | null;

  // Other
  interest_expense: number | null;
  interest_income: number | null;
  other_income: number | null;
  other_expenses: number | null;

  // Profit
  profit_before_tax: number | null;
  income_tax: number | null;
  net_income: number | null;
  net_income_attributable: number | null;
  eps: number | null;

  created_at: string | null;
}

export interface CashFlowStatement {
  id: number;
  stock_id: number;
  period_type: PeriodType;
  year: number;
  quarter: number | null;
  period: string;

  // Operating activities
  operating_cash_flow: number | null;
  net_income_cf: number | null;
  depreciation: number | null;
  changes_in_working_capital: number | null;

  // Investing activities
  investing_cash_flow: number | null;
  capital_expenditure: number | null;
  investments_purchases: number | null;
  investments_sales: number | null;

  // Financing activities
  financing_cash_flow: number | null;
  debt_issued: number | null;
  debt_repaid: number | null;
  dividends_paid: number | null;
  stock_issued: number | null;
  stock_repurchased: number | null;

  // Net change
  net_change_in_cash: number | null;
  beginning_cash: number | null;
  ending_cash: number | null;

  created_at: string | null;
}

export interface FinancialReport {
  stock: Stock;
  balance_sheets: BalanceSheet[];
  income_statements: IncomeStatement[];
  cash_flow_statements: CashFlowStatement[];
}

export interface FetchDataRequest {
  period_type: PeriodType;
  years: number;
}

export interface FetchDataResponse {
  message: string;
  stock: Stock;
  balance_sheets_count: number;
  income_statements_count: number;
  cash_flow_statements_count: number;
}
