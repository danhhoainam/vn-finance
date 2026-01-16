import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { stockApi } from '../services/api';
import type { StockSearchResult } from '../types/financial';

// Debounce delay in milliseconds
const DEBOUNCE_DELAY = 500;

// Custom hook for debounced value
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debouncedValue;
}

interface StockSearchProps {
  onSelect: (symbol: string) => void;
  selectedSymbol: string | null;
}

export function StockSearch({ onSelect, selectedSymbol }: StockSearchProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Debounce the query to avoid excessive API calls
  const debouncedQuery = useDebounce(query, DEBOUNCE_DELAY);

  // Search when debounced query changes
  useEffect(() => {
    const searchStocks = async () => {
      if (debouncedQuery.length < 1) {
        setResults([]);
        return;
      }

      setIsLoading(true);
      try {
        const data = await stockApi.searchStocks(debouncedQuery);
        setResults(data);
        setIsOpen(true);
      } catch (error) {
        console.error('Search failed:', error);
        setResults([]);
      } finally {
        setIsLoading(false);
      }
    };

    searchStocks();
  }, [debouncedQuery]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        !inputRef.current?.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (symbol: string) => {
    onSelect(symbol);
    setQuery('');
    setIsOpen(false);
  };

  return (
    <div className="relative w-full max-w-md">
      <label className="block text-sm font-medium text-gray-700 mb-2">
        {t('search.label')}
      </label>
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value.toUpperCase())}
          onFocus={() => query.length > 0 && setIsOpen(true)}
          placeholder={t('search.placeholder')}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition-colors"
        />
        {isLoading && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="animate-spin h-5 w-5 border-2 border-primary-500 border-t-transparent rounded-full"></div>
          </div>
        )}
      </div>

      {selectedSymbol && (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-sm text-gray-600">{t('search.selected')}:</span>
          <span className="px-3 py-1 bg-primary-100 text-primary-700 rounded-full font-medium">
            {selectedSymbol}
          </span>
        </div>
      )}

      {isOpen && results.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto"
        >
          {results.map((result) => (
            <button
              key={result.symbol}
              onClick={() => handleSelect(result.symbol)}
              className="w-full px-4 py-3 text-left hover:bg-gray-50 focus:bg-gray-50 border-b border-gray-100 last:border-b-0 transition-colors"
            >
              <div className="font-semibold text-gray-900">{result.symbol}</div>
              <div className="text-sm text-gray-500 truncate">
                {result.organName}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
