import { useTranslation } from 'react-i18next';
import type {
  BalanceSheet,
  IncomeStatement,
  CashFlowStatement,
} from '../types/financial';

type ReportType = 'balance_sheet' | 'income_statement' | 'cash_flow';

interface FinancialTableProps {
  reportType: ReportType;
  balanceSheets?: BalanceSheet[];
  incomeStatements?: IncomeStatement[];
  cashFlowStatements?: CashFlowStatement[];
}

const formatNumber = (value: number | null, locale: string): string => {
  if (value === null || value === undefined) return '-';

  // Display the raw number with thousand separators based on locale
  // Vietnamese: 1.234.567,89 | English: 1,234,567.89
  const localeCode = locale === 'vi' ? 'vi-VN' : 'en-US';
  return value.toLocaleString(localeCode, {
    maximumFractionDigits: 10,
  });
};

const getValueClass = (value: number | null): string => {
  if (value === null || value === undefined) return '';
  return value >= 0 ? 'number-positive' : 'number-negative';
};

interface TableRow {
  labelKey: string;
  key: string;
  indent?: number;
}

const balanceSheetRows: TableRow[] = [
  { labelKey: 'balanceSheet.totalAssets', key: 'total_assets' },
  { labelKey: 'balanceSheet.currentAssets', key: 'current_assets', indent: 1 },
  { labelKey: 'balanceSheet.cashAndEquivalents', key: 'cash_and_equivalents', indent: 2 },
  { labelKey: 'balanceSheet.shortTermInvestments', key: 'short_term_investments', indent: 2 },
  { labelKey: 'balanceSheet.accountsReceivable', key: 'accounts_receivable', indent: 2 },
  { labelKey: 'balanceSheet.inventory', key: 'inventory', indent: 2 },
  { labelKey: 'balanceSheet.nonCurrentAssets', key: 'non_current_assets', indent: 1 },
  { labelKey: 'balanceSheet.fixedAssets', key: 'fixed_assets', indent: 2 },
  { labelKey: 'balanceSheet.longTermInvestments', key: 'long_term_investments', indent: 2 },
  { labelKey: 'balanceSheet.totalLiabilities', key: 'total_liabilities' },
  { labelKey: 'balanceSheet.currentLiabilities', key: 'current_liabilities', indent: 1 },
  { labelKey: 'balanceSheet.shortTermDebt', key: 'short_term_debt', indent: 2 },
  { labelKey: 'balanceSheet.accountsPayable', key: 'accounts_payable', indent: 2 },
  { labelKey: 'balanceSheet.nonCurrentLiabilities', key: 'non_current_liabilities', indent: 1 },
  { labelKey: 'balanceSheet.longTermDebt', key: 'long_term_debt', indent: 2 },
  { labelKey: 'balanceSheet.totalEquity', key: 'total_equity' },
  { labelKey: 'balanceSheet.shareCapital', key: 'share_capital', indent: 1 },
  { labelKey: 'balanceSheet.retainedEarnings', key: 'retained_earnings', indent: 1 },
  { labelKey: 'balanceSheet.minorityInterest', key: 'minority_interest', indent: 1 },
];

const incomeStatementRows: TableRow[] = [
  { labelKey: 'incomeStatement.revenue', key: 'revenue' },
  { labelKey: 'incomeStatement.costOfRevenue', key: 'cost_of_revenue' },
  { labelKey: 'incomeStatement.grossProfit', key: 'gross_profit' },
  { labelKey: 'incomeStatement.operatingExpenses', key: 'operating_expenses' },
  { labelKey: 'incomeStatement.sellingExpenses', key: 'selling_expenses', indent: 1 },
  { labelKey: 'incomeStatement.administrativeExpenses', key: 'administrative_expenses', indent: 1 },
  { labelKey: 'incomeStatement.operatingIncome', key: 'operating_income' },
  { labelKey: 'incomeStatement.interestIncome', key: 'interest_income' },
  { labelKey: 'incomeStatement.interestExpense', key: 'interest_expense' },
  { labelKey: 'incomeStatement.otherIncome', key: 'other_income' },
  { labelKey: 'incomeStatement.otherExpenses', key: 'other_expenses' },
  { labelKey: 'incomeStatement.profitBeforeTax', key: 'profit_before_tax' },
  { labelKey: 'incomeStatement.incomeTax', key: 'income_tax' },
  { labelKey: 'incomeStatement.netIncome', key: 'net_income' },
  { labelKey: 'incomeStatement.netIncomeAttributable', key: 'net_income_attributable' },
  { labelKey: 'incomeStatement.eps', key: 'eps' },
];

const cashFlowRows: TableRow[] = [
  { labelKey: 'cashFlow.operatingCashFlow', key: 'operating_cash_flow' },
  { labelKey: 'cashFlow.netIncomeCf', key: 'net_income_cf', indent: 1 },
  { labelKey: 'cashFlow.depreciation', key: 'depreciation', indent: 1 },
  { labelKey: 'cashFlow.changesInWorkingCapital', key: 'changes_in_working_capital', indent: 1 },
  { labelKey: 'cashFlow.investingCashFlow', key: 'investing_cash_flow' },
  { labelKey: 'cashFlow.capitalExpenditure', key: 'capital_expenditure', indent: 1 },
  { labelKey: 'cashFlow.investmentPurchases', key: 'investments_purchases', indent: 1 },
  { labelKey: 'cashFlow.investmentSales', key: 'investments_sales', indent: 1 },
  { labelKey: 'cashFlow.financingCashFlow', key: 'financing_cash_flow' },
  { labelKey: 'cashFlow.debtIssued', key: 'debt_issued', indent: 1 },
  { labelKey: 'cashFlow.debtRepaid', key: 'debt_repaid', indent: 1 },
  { labelKey: 'cashFlow.dividendsPaid', key: 'dividends_paid', indent: 1 },
  { labelKey: 'cashFlow.stockIssued', key: 'stock_issued', indent: 1 },
  { labelKey: 'cashFlow.stockRepurchased', key: 'stock_repurchased', indent: 1 },
  { labelKey: 'cashFlow.netChangeInCash', key: 'net_change_in_cash' },
  { labelKey: 'cashFlow.beginningCash', key: 'beginning_cash' },
  { labelKey: 'cashFlow.endingCash', key: 'ending_cash' },
];

export function FinancialTable({
  reportType,
  balanceSheets = [],
  incomeStatements = [],
  cashFlowStatements = [],
}: FinancialTableProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  const getRows = (): TableRow[] => {
    switch (reportType) {
      case 'balance_sheet':
        return balanceSheetRows;
      case 'income_statement':
        return incomeStatementRows;
      case 'cash_flow':
        return cashFlowRows;
    }
  };

  const getData = (): (BalanceSheet | IncomeStatement | CashFlowStatement)[] => {
    switch (reportType) {
      case 'balance_sheet':
        return balanceSheets;
      case 'income_statement':
        return incomeStatements;
      case 'cash_flow':
        return cashFlowStatements;
    }
  };

  const rows = getRows();
  const data = getData();

  if (data.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        {t('common.noData')}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="financial-table">
        <thead>
          <tr>
            <th className="sticky left-0 bg-gray-100 z-10 min-w-[250px]">
              {t('table.item')}
            </th>
            {data.map((item) => (
              <th key={item.id} className="min-w-[140px]">
                {item.period}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td
                className="sticky left-0 bg-white z-10 font-medium"
                style={{ paddingLeft: `${(row.indent ?? 0) * 16 + 16}px` }}
              >
                {t(row.labelKey)}
              </td>
              {data.map((item) => {
                const value = (item as unknown as Record<string, unknown>)[row.key] as number | null;
                return (
                  <td
                    key={item.id}
                    className={`text-right ${getValueClass(value)}`}
                  >
                    {formatNumber(value, locale)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
