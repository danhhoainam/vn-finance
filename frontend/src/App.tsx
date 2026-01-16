import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { StockSearch } from './components/StockSearch';
import { FinancialTable } from './components/FinancialTable';
import { stockApi } from './services/api';
import type {
  PeriodType,
  BalanceSheet,
  IncomeStatement,
  CashFlowStatement,
  Stock,
} from './types/financial';

type TabType = 'balance_sheet' | 'income_statement' | 'cash_flow';

function App() {
  const { t, i18n } = useTranslation();
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [stock, setStock] = useState<Stock | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('balance_sheet');
  const [periodType, setPeriodType] = useState<PeriodType>('annual');
  const [selectedYears, setSelectedYears] = useState<number[]>([]);
  const [availableYears, setAvailableYears] = useState<number[]>([]);

  const [balanceSheets, setBalanceSheets] = useState<BalanceSheet[]>([]);
  const [incomeStatements, setIncomeStatements] = useState<IncomeStatement[]>([]);
  const [cashFlowStatements, setCashFlowStatements] = useState<CashFlowStatement[]>([]);

  const [isLoading, setIsLoading] = useState(false);
  const [fetchStatus, setFetchStatus] = useState<string>('idle');
  const [error, setError] = useState<string | null>(null);

  const language = i18n.language as 'vi' | 'en';

  const changeLanguage = (lang: 'vi' | 'en') => {
    i18n.changeLanguage(lang);
  };

  const getErrorMessage = (err: unknown, defaultKey: string): string => {
    // Check for timeout error
    if (axios.isAxiosError(err) && err.code === 'ECONNABORTED') {
      return t('common.timeoutError');
    }
    return t(defaultKey);
  };

  const handleStockSelect = async (symbol: string) => {
    setSelectedSymbol(symbol);
    setError(null);
    setIsLoading(true);
    setFetchStatus('loading');

    try {
      const reports = await stockApi.getAllReports(symbol, undefined, periodType, language);
      setStock(reports.stock);
      setBalanceSheets(reports.balance_sheets);
      setIncomeStatements(reports.income_statements);
      setCashFlowStatements(reports.cash_flow_statements);
      setFetchStatus(reports.fetch_status || 'completed');
      updateAvailableYears(reports.balance_sheets, reports.income_statements, reports.cash_flow_statements);
    } catch (err) {
      setError(getErrorMessage(err, 'common.fetchError'));
      setFetchStatus('error');
      console.error('Fetch error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const refreshData = async () => {
    if (!selectedSymbol) return;

    setIsLoading(true);
    setFetchStatus('fetching');
    setError(null);

    try {
      await stockApi.fetchStockData(selectedSymbol, {
        period_type: periodType,
        years: 6,
      }, language);

      const reports = await stockApi.getAllReports(selectedSymbol, undefined, periodType, language);
      setStock(reports.stock);
      setBalanceSheets(reports.balance_sheets);
      setIncomeStatements(reports.income_statements);
      setCashFlowStatements(reports.cash_flow_statements);
      setFetchStatus('completed');
      updateAvailableYears(reports.balance_sheets, reports.income_statements, reports.cash_flow_statements);
    } catch (err) {
      setError(getErrorMessage(err, 'common.refreshError'));
      setFetchStatus('error');
      console.error('Refresh error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const updateAvailableYears = (
    bs: BalanceSheet[],
    is: IncomeStatement[],
    cf: CashFlowStatement[]
  ) => {
    const years = new Set<number>();
    [...bs, ...is, ...cf].forEach((item) => years.add(item.year));
    setAvailableYears(Array.from(years).sort((a, b) => b - a));
  };

  useEffect(() => {
    if (selectedSymbol) {
      loadReports();
    }
  }, [periodType]);

  const loadReports = async () => {
    if (!selectedSymbol) return;

    setIsLoading(true);
    try {
      const reports = await stockApi.getAllReports(
        selectedSymbol,
        undefined,
        periodType,
        language
      );
      setStock(reports.stock);
      setBalanceSheets(reports.balance_sheets);
      setIncomeStatements(reports.income_statements);
      setCashFlowStatements(reports.cash_flow_statements);
      updateAvailableYears(reports.balance_sheets, reports.income_statements, reports.cash_flow_statements);
    } catch (err) {
      console.error('Load error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleYear = (year: number) => {
    setSelectedYears((prev) =>
      prev.includes(year)
        ? prev.filter((y) => y !== year)
        : [...prev, year].sort((a, b) => b - a)
    );
  };

  const selectAllYears = () => {
    setSelectedYears([]);
  };

  // Filter data by selected years (empty array = all years)
  const filteredBalanceSheets = selectedYears.length === 0
    ? balanceSheets
    : balanceSheets.filter((bs) => selectedYears.includes(bs.year));

  const filteredIncomeStatements = selectedYears.length === 0
    ? incomeStatements
    : incomeStatements.filter((is) => selectedYears.includes(is.year));

  const filteredCashFlowStatements = selectedYears.length === 0
    ? cashFlowStatements
    : cashFlowStatements.filter((cf) => selectedYears.includes(cf.year));

  const tabs: { id: TabType; labelKey: string }[] = [
    { id: 'balance_sheet', labelKey: 'tabs.balanceSheet' },
    { id: 'income_statement', labelKey: 'tabs.incomeStatement' },
    { id: 'cash_flow', labelKey: 'tabs.cashFlow' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{t('common.title')}</h1>
              <p className="mt-1 text-sm text-gray-500">{t('common.subtitle')}</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => changeLanguage('vi')}
                className={`px-3 py-1 text-sm rounded ${
                  language === 'vi'
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                VI
              </button>
              <button
                onClick={() => changeLanguage('en')}
                className={`px-3 py-1 text-sm rounded ${
                  language === 'en'
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                EN
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Search and Filters */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <div className="flex flex-wrap gap-6 items-end">
            <StockSearch
              onSelect={handleStockSelect}
              selectedSymbol={selectedSymbol}
            />

            {selectedSymbol && (
              <>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {t('period.type')}
                  </label>
                  <div className="flex rounded-lg overflow-hidden border border-gray-300">
                    <button
                      onClick={() => setPeriodType('annual')}
                      className={`px-4 py-2 text-sm font-medium transition-colors ${
                        periodType === 'annual'
                          ? 'bg-primary-600 text-white'
                          : 'bg-white text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {t('period.annual')}
                    </button>
                    <button
                      onClick={() => setPeriodType('quarter')}
                      className={`px-4 py-2 text-sm font-medium transition-colors border-l border-gray-300 ${
                        periodType === 'quarter'
                          ? 'bg-primary-600 text-white'
                          : 'bg-white text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {t('period.quarterly')}
                    </button>
                  </div>
                </div>

                {availableYears.length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      {t('period.year')}
                    </label>
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={selectAllYears}
                        className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                          selectedYears.length === 0
                            ? 'bg-primary-600 text-white'
                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }`}
                      >
                        {t('period.allYears')}
                      </button>
                      {availableYears.map((year) => (
                        <button
                          key={year}
                          onClick={() => toggleYear(year)}
                          className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                            selectedYears.includes(year)
                              ? 'bg-primary-600 text-white'
                              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                          }`}
                        >
                          {year}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <button
                  onClick={refreshData}
                  disabled={isLoading}
                  className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isLoading ? t('actions.fetching') : t('actions.refresh')}
                </button>
              </>
            )}
          </div>

          {stock && (
            <div className="mt-4 pt-4 border-t">
              <div className="flex items-center gap-4">
                <span className="text-lg font-semibold">{stock.symbol}</span>
                {stock.name && (
                  <span className="text-gray-600">{stock.name}</span>
                )}
                {stock.exchange && (
                  <span className="px-2 py-1 bg-gray-100 text-gray-600 text-sm rounded">
                    {stock.exchange}
                  </span>
                )}
                {fetchStatus === 'fetching' && (
                  <span className="px-2 py-1 bg-yellow-100 text-yellow-700 text-sm rounded animate-pulse">
                    {t('status.fetchingData')}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
            {error}
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin h-8 w-8 border-4 border-primary-500 border-t-transparent rounded-full"></div>
            <span className="ml-3 text-gray-600">
              {fetchStatus === 'fetching' ? t('status.fetchingData') : t('common.loading')}
            </span>
          </div>
        )}

        {/* Tabs and Table */}
        {!isLoading && selectedSymbol && (
          <div className="bg-white rounded-lg shadow-sm overflow-hidden">
            <div className="border-b">
              <nav className="flex">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`px-6 py-4 text-sm font-medium transition-colors ${
                      activeTab === tab.id
                        ? 'border-b-2 border-primary-600 text-primary-600'
                        : 'text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    {t(tab.labelKey)}
                  </button>
                ))}
              </nav>
            </div>

            <div className="p-6">
              <FinancialTable
                reportType={activeTab}
                balanceSheets={filteredBalanceSheets}
                incomeStatements={filteredIncomeStatements}
                cashFlowStatements={filteredCashFlowStatements}
              />
            </div>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !selectedSymbol && (
          <div className="bg-white rounded-lg shadow-sm p-12 text-center">
            <div className="text-gray-400 mb-4">
              <svg
                className="w-16 h-16 mx-auto"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">
              {t('emptyState.title')}
            </h3>
            <p className="text-gray-500">{t('emptyState.description')}</p>
          </div>
        )}
      </main>

      <footer className="bg-white border-t mt-12">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <p className="text-center text-sm text-gray-500">{t('common.dataSource')}</p>
        </div>
      </footer>
    </div>
  );
}

export default App;
