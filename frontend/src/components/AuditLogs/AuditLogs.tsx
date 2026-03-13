import { useState, useEffect } from 'react';
import type { AuditLogEntry } from '../../types/audit';
import { fetchAuditLogs } from '../../api';

interface AuditLogsProps {
  documentId: string | null;
}

export default function AuditLogs({ documentId }: AuditLogsProps) {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterDoc, setFilterDoc] = useState<string>(documentId ?? '');
  const [filterFromDate, setFilterFromDate] = useState<string>('');
  const [filterToDate, setFilterToDate] = useState<string>('');
  const [sortNewestFirst, setSortNewestFirst] = useState(true);
  const [sectionOpen, setSectionOpen] = useState(false);

  useEffect(() => {
    setFilterDoc(documentId ?? '');
  }, [documentId]);

  useEffect(() => {
    setLoading(true);
    const docFilter = filterDoc || undefined;
    fetchAuditLogs(docFilter).then((list) => {
      setEntries(list);
      setLoading(false);
    });
  }, [filterDoc]);

  const filtered = entries.filter((e) => {
    const t = new Date(e.timestamp).getTime();
    if (filterFromDate) {
      const fromStart = new Date(filterFromDate).setHours(0, 0, 0, 0);
      if (t < fromStart) return false;
    }
    if (filterToDate) {
      const toEnd = new Date(filterToDate).setHours(23, 59, 59, 999);
      if (t > toEnd) return false;
    }
    return true;
  });

  const sorted = [...filtered].sort((a, b) => {
    const ta = new Date(a.timestamp).getTime();
    const tb = new Date(b.timestamp).getTime();
    return sortNewestFirst ? tb - ta : ta - tb;
  });

  return (
    <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
      <button
        type="button"
        onClick={() => setSectionOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 text-left mb-4 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 rounded"
        aria-expanded={sectionOpen}
      >
        <h2 className="text-lg font-semibold text-slate-800">5. Audit Logs</h2>
        <span className="shrink-0 text-slate-500" aria-hidden>
          {sectionOpen ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          ) : (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
          )}
        </span>
      </button>
      {sectionOpen && (
      <>
      <div className="flex flex-wrap gap-3 sm:gap-4 mb-4">
        <label className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2 text-sm min-w-0">
          <span className="text-slate-600 shrink-0">Filter by document:</span>
          <input
            type="text"
            value={filterDoc}
            onChange={(e) => setFilterDoc(e.target.value)}
            placeholder="Document ID or leave empty for all"
            className="border border-slate-300 rounded px-2 py-1 w-full sm:w-48 min-w-0"
          />
        </label>
        <label className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2 text-sm">
          <span className="text-slate-600 shrink-0">From date:</span>
          <input
            type="date"
            value={filterFromDate}
            onChange={(e) => setFilterFromDate(e.target.value)}
            className="border border-slate-300 rounded px-2 py-1 w-full sm:w-40 min-w-0"
          />
        </label>
        <label className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2 text-sm">
          <span className="text-slate-600 shrink-0">To date:</span>
          <input
            type="date"
            value={filterToDate}
            onChange={(e) => setFilterToDate(e.target.value)}
            className="border border-slate-300 rounded px-2 py-1 w-full sm:w-40 min-w-0"
          />
        </label>
        <label className="flex items-center gap-2 text-sm shrink-0">
          <input
            type="checkbox"
            checked={sortNewestFirst}
            onChange={(e) => setSortNewestFirst(e.target.checked)}
          />
          <span className="text-slate-600">Newest first</span>
        </label>
      </div>
      {loading ? (
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-slate-800" />
        </div>
      ) : sorted.length === 0 ? (
        <p className="text-slate-500">No audit entries.</p>
      ) : (
        <div className="overflow-x-auto border border-slate-200 rounded">
          <table className="w-full text-sm border-collapse border border-slate-200">
            <thead>
              <tr className="bg-slate-100">
                <th className="border border-slate-200 px-3 py-2 text-left">Timestamp</th>
                <th className="border border-slate-200 px-3 py-2 text-left">Document</th>
                <th className="border border-slate-200 px-3 py-2 text-left">Parser version</th>
                <th className="border border-slate-200 px-3 py-2 text-left">Validation result</th>
                <th className="border border-slate-200 px-3 py-2 text-left">Reviewer</th>
                <th className="border border-slate-200 px-3 py-2 text-left">Action</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50">
                  <td className="border border-slate-200 px-3 py-2">{new Date(e.timestamp).toLocaleString()}</td>
                  <td className="border border-slate-200 px-3 py-2">{e.documentName ?? e.documentId}</td>
                  <td className="border border-slate-200 px-3 py-2">{e.parserVersion}</td>
                  <td className="border border-slate-200 px-3 py-2">
                    {e.validationResult === 'Human Verified' ? (
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                        Human Verified
                      </span>
                    ) : e.validationResult === 'Pending Review' ? (
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">
                        Pending Review
                      </span>
                    ) : (
                      e.validationResult
                    )}
                  </td>
                  <td className="border border-slate-200 px-3 py-2">{e.reviewer}</td>
                  <td className="border border-slate-200 px-3 py-2">{e.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      </>
      )}
    </section>
  );
}
