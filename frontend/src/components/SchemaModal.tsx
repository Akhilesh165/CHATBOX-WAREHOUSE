'use client';

import React, { useState, useEffect } from 'react';
import { TableProperties, X, Check, Database, Layers, Boxes, Eye } from 'lucide-react';

interface SchemaModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SchemaModal: React.FC<SchemaModalProps> = ({ isOpen, onClose }) => {
  const [schemaData, setSchemaData] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<string>('dbo.ZWMS_INVENTORY');

  useEffect(() => {
    if (isOpen && !schemaData) {
      fetch('/api/schema')
        .then((res) => res.json())
        .then((data) => {
          setSchemaData(data.tables);
        })
        .catch((err) => console.error('Failed to load schema', err));
    }
  }, [isOpen, schemaData]);

  if (!isOpen) return null;

  const tableKeys = schemaData ? Object.keys(schemaData) : [
    'dbo.ZWMS_INVENTORY',
    'dbo.ZWMS_BIN_MASTER',
    'dbo.ZWMS_MATERIAL_MASTER',
    'dbo.vw_WMS_InventoryEnriched'
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-3xl w-full overflow-hidden flex flex-col max-h-[85vh]">
        {/* Modal Header */}
        <div className="px-5 py-4 bg-slate-900 text-white flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 bg-sky-500/20 text-sky-400 rounded-lg">
              <TableProperties className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold">Authoritative Schema Reference</h3>
              <p className="text-[11px] text-slate-400">Read-Only SQL Server Tables & Semantic Views</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab switcher */}
        <div className="flex items-center space-x-1 px-4 py-2 bg-slate-100 border-b border-slate-200 overflow-x-auto">
          {tableKeys.map((tbl) => (
            <button
              key={tbl}
              onClick={() => setActiveTab(tbl)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition ${
                activeTab === tbl
                  ? 'bg-white text-sky-700 shadow-xs border border-slate-200'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
              }`}
            >
              {tbl}
            </button>
          ))}
        </div>

        {/* Table details body */}
        <div className="p-5 flex-1 overflow-y-auto space-y-4">
          {schemaData && schemaData[activeTab] ? (
            <div>
              <div className="bg-sky-50 border border-sky-200/80 rounded-xl p-3 mb-4">
                <div className="text-xs font-bold text-sky-900">
                  {activeTab}
                </div>
                <div className="text-[11px] text-sky-700 mt-0.5">
                  <strong>Source:</strong> {schemaData[activeTab].source}
                </div>
                <div className="text-[11px] text-sky-800 mt-0.5">
                  {schemaData[activeTab].description}
                </div>
              </div>

              {schemaData[activeTab].columns && (
                <div>
                  <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
                    Available Columns ({schemaData[activeTab].columns.length})
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {schemaData[activeTab].columns.map((col: string) => (
                      <div
                        key={col}
                        className="px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-700 flex items-center space-x-1.5"
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-sky-500"></span>
                        <span className="truncate">{col}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="p-8 text-center text-xs text-slate-400">
              Loading schema definitions...
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center space-x-1.5">
            <Database className="w-3.5 h-3.5 text-emerald-600" />
            <span>Enforced by SQLGlot table allowlist</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded-lg font-medium transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
