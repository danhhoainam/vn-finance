import axios from 'axios';
import type {
  Stock,
  StockSearchResult,
  BalanceSheet,
  IncomeStatement,
  CashFlowStatement,
  FetchDataRequest,
  FetchDataResponse,
  PeriodType,
} from '../types/financial';

const API_URL = import.meta.env.VITE_API_URL || '';

// Timeout configuration (in milliseconds)
const DEFAULT_TIMEOUT = 30000; // 30 seconds
const FETCH_TIMEOUT = 60000;   // 60 seconds for data fetching

const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: DEFAULT_TIMEOUT,
});

export interface ReportsResponse {
  stock: Stock | null;
  balance_sheets: BalanceSheet[];
  income_statements: IncomeStatement[];
  cash_flow_statements: CashFlowStatement[];
  status: string;
  fetch_status: string;
}

export const stockApi = {
  // List all stocks in database
  listStocks: async (): Promise<Stock[]> => {
    const response = await api.get<Stock[]>('/stocks');
    return response.data;
  },

  // Search stocks using vnstock
  searchStocks: async (query: string): Promise<StockSearchResult[]> => {
    const response = await api.get<StockSearchResult[]>('/stocks/search', {
      params: { q: query },
    });
    return response.data;
  },

  // Get stock details
  getStock: async (symbol: string): Promise<Stock> => {
    const response = await api.get<Stock>(`/stocks/${symbol}`);
    return response.data;
  },

  // Fetch and store data from vnstock
  fetchStockData: async (
    symbol: string,
    request?: FetchDataRequest,
    lang: string = 'vi'
  ): Promise<FetchDataResponse> => {
    const response = await api.post<FetchDataResponse>(
      `/stocks/${symbol}/fetch`,
      request || { period_type: 'annual', years: 6 },
      { params: { lang }, timeout: FETCH_TIMEOUT }
    );
    return response.data;
  },

  // Get balance sheets
  getBalanceSheets: async (
    symbol: string,
    year?: number,
    periodType?: PeriodType
  ): Promise<BalanceSheet[]> => {
    const params: Record<string, string | number> = {};
    if (year) params.year = year;
    if (periodType) params.period_type = periodType;

    const response = await api.get<BalanceSheet[]>(
      `/stocks/${symbol}/balance-sheet`,
      { params }
    );
    return response.data;
  },

  // Get income statements
  getIncomeStatements: async (
    symbol: string,
    year?: number,
    periodType?: PeriodType
  ): Promise<IncomeStatement[]> => {
    const params: Record<string, string | number> = {};
    if (year) params.year = year;
    if (periodType) params.period_type = periodType;

    const response = await api.get<IncomeStatement[]>(
      `/stocks/${symbol}/income-statement`,
      { params }
    );
    return response.data;
  },

  // Get cash flow statements
  getCashFlowStatements: async (
    symbol: string,
    year?: number,
    periodType?: PeriodType
  ): Promise<CashFlowStatement[]> => {
    const params: Record<string, string | number> = {};
    if (year) params.year = year;
    if (periodType) params.period_type = periodType;

    const response = await api.get<CashFlowStatement[]>(
      `/stocks/${symbol}/cash-flow`,
      { params }
    );
    return response.data;
  },

  // Get all reports for a stock
  getAllReports: async (
    symbol: string,
    year?: number,
    periodType: PeriodType = 'annual',
    lang: string = 'vi'
  ): Promise<ReportsResponse> => {
    const params: Record<string, string | number | boolean> = {
      period_type: periodType,
      lang,
      auto_fetch: true,
    };
    if (year) params.year = year;

    const response = await api.get<ReportsResponse>(
      `/stocks/${symbol}/reports`,
      { params, timeout: FETCH_TIMEOUT }
    );
    return response.data;
  },

  // Get fetch status
  getFetchStatus: async (symbol: string): Promise<{ symbol: string; status: string }> => {
    const response = await api.get<{ symbol: string; status: string }>(`/stocks/${symbol}/status`);
    return response.data;
  },

  // Delete a stock
  deleteStock: async (symbol: string): Promise<void> => {
    await api.delete(`/stocks/${symbol}`);
  },
};

export default api;
