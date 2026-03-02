import { useState, useEffect } from 'react';
import type { ValidationItem } from '../../types/validation';
import { fetchValidationItems, updateValidationStatus, fetchPageAccuracy } from '../../api';

interface ValidationConsoleProps {
  documentId: string | null;
  documentValidationStatus?: string;
}

export default function ValidationConsole({ documentId, documentValidationStatus }: ValidationConsoleProps) {
  const [items, setItems] = useState<ValidationItem[]>([]);
  const [pageAccuracy, setPageAccuracy] = useState<{ pageNumber: number; accuracyPct: number; status: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [commentInputs, setCommentInputs] = useState<Record<string, string>>({});

  useEffect(() => {
    setLoading(true);
    fetchValidationItems(documentId ?? undefined).then((list) => {
      setItems(list);
      setLoading(false);
    });
  }, [documentId]);

  useEffect(() => {
    if (!documentId) {
      setPageAccuracy([]);
      return;
    }
    fetchPageAccuracy(documentId)
      .then((list) => setPageAccuracy(list.map((a) => ({ pageNumber: a.pageNumber, accuracyPct: a.accuracyPct, status: a.status }))))
      .catch(() => setPageAccuracy([]));
  }, [documentId]);

  const documentConfidence = pageAccuracy.length > 0
    ? pageAccuracy.reduce((s, a) => s + a.accuracyPct, 0) / pageAccuracy.length
    : null;
  const anyPageBelow98 = pageAccuracy.some((a) => a.accuracyPct < 98);
  const approveDisabled = documentValidationStatus === 'validation_failed' || documentValidationStatus === 'screenshot_failed' || anyPageBelow98;

  const handleApprove = async (itemId: string) => {
    const comment = commentInputs[itemId];
    const updated = (await updateValidationStatus(itemId, 'approved', 'Current User', comment)) as ValidationItem | undefined;
    setItems((prev) => (updated ? prev.map((i) => (i.id === itemId ? updated : i)) : prev.map((i) => (i.id === itemId ? { ...i, status: 'approved' as const, reviewer: 'Current User' } : i))));
    setCommentInputs((prev) => ({ ...prev, [itemId]: '' }));
  };

  const handleReject = async (itemId: string) => {
    const comment = commentInputs[itemId];
    const updated = (await updateValidationStatus(itemId, 'rejected', 'Current User', comment)) as ValidationItem | undefined;
    setItems((prev) => (updated ? prev.map((i) => (i.id === itemId ? updated : i)) : prev.map((i) => (i.id === itemId ? { ...i, status: 'rejected' as const, reviewer: 'Current User' } : i))));
    setCommentInputs((prev) => ({ ...prev, [itemId]: '' }));
  };

  const addComment = (itemId: string) => {
    const text = commentInputs[itemId]?.trim();
    if (!text) return;
    updateValidationStatus(itemId, items.find((i) => i.id === itemId)!.status, undefined, text);
    setItems((prev) =>
      prev.map((i) =>
        i.id === itemId
          ? {
              ...i,
              comments: [
                ...i.comments,
                { id: `c-${Date.now()}`, author: 'Current User', text, createdAt: new Date().toISOString() },
              ],
            }
          : i
      )
    );
    setCommentInputs((prev) => ({ ...prev, [itemId]: '' }));
  };

  return (
    <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
      <h2 className="text-lg font-semibold text-slate-800 mb-4">4. Validation Console</h2>

      {documentId && (
        <div className="mb-6">
          <h3 className="text-sm font-medium text-slate-700 mb-2">Page-Level Validation Report</h3>
          {pageAccuracy.length === 0 ? (
            <p className="text-slate-500 text-sm">No page accuracy data (PDF only, computed after extraction).</p>
          ) : (
            <>
              {documentConfidence != null && (
                <div className="mb-3">
                  <div className="text-xs text-slate-500 mb-1">Document confidence (avg page accuracy)</div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 max-w-[200px] h-3 bg-slate-200 rounded overflow-hidden">
                      <div
                        className={`h-full ${documentConfidence >= 98 ? 'bg-green-500' : documentConfidence >= 95 ? 'bg-amber-500' : 'bg-red-500'}`}
                        style={{ width: `${Math.min(100, documentConfidence)}%` }}
                      />
                    </div>
                    <span className="text-sm font-medium">{documentConfidence.toFixed(1)}%</span>
                  </div>
                </div>
              )}
              <div className="overflow-x-auto border border-slate-200 rounded">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-100">
                      <th className="text-left p-2">Page</th>
                      <th className="text-left p-2">Accuracy %</th>
                      <th className="text-left p-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageAccuracy.map((a) => (
                      <tr
                        key={a.pageNumber}
                        className={a.status === 'ERROR' ? 'bg-red-50' : a.status === 'WARNING' ? 'bg-amber-50' : ''}
                      >
                        <td className="p-2">{a.pageNumber}</td>
                        <td className="p-2">{a.accuracyPct.toFixed(2)}%</td>
                        <td className="p-2">
                          <span className={a.status === 'ERROR' ? 'text-red-700 font-medium' : a.status === 'WARNING' ? 'text-amber-700' : ''}>
                            {a.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {anyPageBelow98 && (
                <p className="mt-2 text-sm text-red-700">
                  Page(s) below 98% threshold — approval disabled until resolved.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-slate-800" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-slate-500">No validation items in the queue.</p>
      ) : (
        <ul className="space-y-3 sm:space-y-4">
          {items.map((item) => (
            <li key={item.id} className="border border-slate-200 rounded p-3 sm:p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <span className="font-medium">{item.documentName}</span>
                <span
                  className={`px-2 py-0.5 rounded text-sm ${
                    item.status === 'approved' ? 'bg-green-100 text-green-800' : item.status === 'rejected' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-800'
                  }`}
                >
                  {item.status}
                </span>
              </div>
              <div className="flex items-center gap-4 mb-2">
                <div className="flex-1">
                  <div className="text-xs text-slate-500 mb-1">Confidence</div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-slate-200 rounded overflow-hidden max-w-[120px]">
                      <div
                        className={`h-full ${
                          item.confidence >= 98 ? 'bg-green-500' : item.confidence >= 90 ? 'bg-amber-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${item.confidence}%` }}
                      />
                    </div>
                    <span className="text-sm font-medium">{item.confidence}%</span>
                  </div>
                </div>
              </div>
              <p className="text-sm text-slate-600 mb-3">{item.conflictReason}</p>
              {item.status === 'pending' && (
                <div className="flex gap-2 mb-3">
                  <button
                    type="button"
                    onClick={() => handleApprove(item.id)}
                    disabled={approveDisabled && item.documentId === documentId}
                    className="px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => handleReject(item.id)}
                    className="px-3 py-1.5 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
                  >
                    Reject
                  </button>
                </div>
              )}
              <div>
                <button
                  type="button"
                  onClick={() => setExpandedId((id) => (id === item.id ? null : item.id))}
                  className="text-sm text-slate-600 hover:text-slate-800"
                >
                  {expandedId === item.id ? 'Hide' : 'Show'} comment log ({item.comments.length})
                </button>
                {expandedId === item.id && (
                  <div className="mt-2 border-t border-slate-200 pt-2">
                    <ul className="space-y-1 mb-2">
                      {item.comments.map((c) => (
                        <li key={c.id} className="text-sm">
                          <span className="font-medium text-slate-700">{c.author}:</span> {c.text}{' '}
                          <span className="text-slate-400 text-xs">{new Date(c.createdAt).toLocaleString()}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="flex flex-wrap sm:flex-nowrap gap-2 min-w-0">
                      <input
                        type="text"
                        value={commentInputs[item.id] ?? ''}
                        onChange={(e) => setCommentInputs((prev) => ({ ...prev, [item.id]: e.target.value }))}
                        placeholder="Add a comment..."
                        className="flex-1 min-w-0 border border-slate-300 rounded px-2 py-1 text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => addComment(item.id)}
                        className="px-2 py-1 bg-slate-600 text-white rounded text-sm hover:bg-slate-700"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
