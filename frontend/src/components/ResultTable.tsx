import React, { useState, useMemo } from 'react';
import { Download, ChevronLeft, ChevronRight, Search, Table as TableIcon } from 'lucide-react';

interface ResultTableProps {
  rows: Array<Record<string, any>>;
  pageSize?: number;
}

export const ResultTable: React.FC<ResultTableProps> = ({ rows, pageSize = 8 }) => {
  const [currentPage, setCurrentPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState('');

  if (!rows || rows.length === 0) return null;

  const columns = Object.keys(rows[0]);

  // Filter rows
  const filteredRows = useMemo(() => {
    if (!searchTerm.trim()) return rows;
    const term = searchTerm.toLowerCase();
    return rows.filter((row) =>
      columns.some((col) => {
        const val = row[col];
        return val !== null && val !== undefined && String(val).toLowerCase().includes(term);
      })
    );
  }, [rows, searchTerm, columns]);

  const totalPages = Math.ceil(filteredRows.length / pageSize) || 1;
  const startIndex = (currentPage - 1) * pageSize;
  const paginatedRows = filteredRows.slice(startIndex, startIndex + pageSize);

  const exportToCSV = () => {
    if (rows.length === 0) return;
    const headerLine = columns.join(',');
    const rowLines = rows.map((row) =>
      columns
        .map((col) => {
          let val = row[col];
          if (val === null || val === undefined) return '""';
          val = String(val).replace(/"/g, '""');
          return `"${val}"`;
        })
        .join(',')
    );
    const csvContent = [headerLine, ...rowLines].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `warehouse_inventory_export_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="w-full bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden my-3 transition-colors">
      {/* Table Header Controls */}
      <div className="flex flex-wrap items-center justify-between p-3 bg-slate-50 dark:bg-slate-850 border-b border-slate-200 dark:border-slate-800 gap-2">
        <div className="flex items-center space-x-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
          <TableIcon className="w-4 h-4 text-sky-600 dark:text-sky-400" />
          <span>Results Data ({rows.length} {rows.length === 1 ? 'row' : 'rows'})</span>
        </div>
        <div className="flex items-center space-x-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-slate-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder="Search in table..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setCurrentPage(1);
              }}
              className="pl-8 pr-2.5 py-1 text-xs border border-slate-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </div>
          <button
            onClick={exportToCSV}
            className="flex items-center space-x-1 px-2.5 py-1 text-xs font-medium text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-750 transition"
            title="Download as CSV"
          >
            <Download className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {/* Table Scroll Area */}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-left text-xs">
          <thead className="bg-slate-50 dark:bg-slate-850 font-semibold text-slate-600 dark:text-slate-300">
            <tr>
              {columns.map((col) => (
                <th key={col} className="px-3.5 py-2.5 whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 bg-white dark:bg-slate-900">
            {paginatedRows.length > 0 ? (
              paginatedRows.map((row, rowIdx) => (
                <tr key={rowIdx} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/50 transition">
                  {columns.map((col) => {
                    const cellVal = row[col];
                    const isNumeric = typeof cellVal === 'number';
                    return (
                      <td
                        key={col}
                        className={`px-3.5 py-2 text-slate-700 dark:text-slate-200 whitespace-nowrap ${
                          isNumeric ? 'font-mono' : ''
                        }`}
                      >
                        {cellVal !== null && cellVal !== undefined
                          ? isNumeric
                            ? cellVal.toLocaleString()
                            : String(cellVal)
                          : '-'}
                      </td>
                    );
                  })}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns.length} className="px-4 py-4 text-center text-slate-400 dark:text-slate-500">
                  No matching records found in filtered results.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-3.5 py-2 bg-slate-50 dark:bg-slate-850 border-t border-slate-200 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-300">
          <div>
            Showing <span className="font-semibold">{startIndex + 1}</span> to{' '}
            <span className="font-semibold">
              {Math.min(startIndex + pageSize, filteredRows.length)}
            </span>{' '}
            of <span className="font-semibold">{filteredRows.length}</span> entries
          </div>
          <div className="flex items-center space-x-1.5">
            <button
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              className="p-1 border border-slate-300 dark:border-slate-700 rounded hover:bg-slate-200 dark:hover:bg-slate-800 disabled:opacity-40 transition"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <span className="px-2 text-xs font-medium">
              Page {currentPage} of {totalPages}
            </span>
            <button
              disabled={currentPage >= totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              className="p-1 border border-slate-300 dark:border-slate-700 rounded hover:bg-slate-200 dark:hover:bg-slate-800 disabled:opacity-40 transition"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
