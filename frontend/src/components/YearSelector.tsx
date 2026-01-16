import { useTranslation } from 'react-i18next';
import type { PeriodType } from '../types/financial';

interface YearSelectorProps {
  years: number[];
  selectedYear: number | null;
  onYearChange: (year: number | null) => void;
  periodType: PeriodType;
  onPeriodTypeChange: (type: PeriodType) => void;
}

export function YearSelector({
  years,
  selectedYear,
  onYearChange,
  periodType,
  onPeriodTypeChange,
}: YearSelectorProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center gap-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          {t('period.type')}
        </label>
        <div className="flex rounded-lg overflow-hidden border border-gray-300">
          <button
            onClick={() => onPeriodTypeChange('annual')}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              periodType === 'annual'
                ? 'bg-primary-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            {t('period.annual')}
          </button>
          <button
            onClick={() => onPeriodTypeChange('quarter')}
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

      {years.length > 0 && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            {t('period.year')}
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => onYearChange(null)}
              className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                selectedYear === null
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {t('period.allYears')}
            </button>
            {years.map((year) => (
              <button
                key={year}
                onClick={() => onYearChange(year)}
                className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                  selectedYear === year
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
    </div>
  );
}
