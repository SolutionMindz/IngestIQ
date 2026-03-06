import { useEffect, useState, useCallback } from 'react';
import type { A2ITaskDetail, DiffItem, DiffAction } from '../../types/a2i';
import { fetchA2ITaskDetail, submitA2ICorrection, screenshotUrl } from '../../api';
import DiffViewer from './DiffViewer';

interface ReviewTaskProps {
  taskId: string;
  reviewerId: string;
  onComplete: () => void;
}

function highlightDiffs(text: string, diffItems: DiffItem[]): React.ReactNode[] {
  if (!text || diffItems.length === 0) return [text];

  // Build a set of textract words that differ
  const diffWords = new Set(
    diffItems
      .filter((d) => d.textractValue)
      .map((d) => d.textractValue.toLowerCase())
  );

  const words = text.split(/(\s+)/);
  return words.map((word, i) => {
    const clean = word.trim().toLowerCase();
    if (clean && diffWords.has(clean)) {
      return (
        <mark key={i} className="bg-red-200 text-red-900 rounded px-0.5">
          {word}
        </mark>
      );
    }
    return word;
  });
}

function assembleCorrection(task: A2ITaskDetail, diffItems: DiffItem[]): string {
  // Start from native text; apply diff item decisions
  const base = task.nativeTextSnapshot ?? task.originalTextractText ?? '';
  if (diffItems.length === 0) return base;

  const words = base.split(/\s+/);
  const result: string[] = [];

  let i = 0;
  while (i < words.length) {
    const diffForIndex = diffItems.find((d) => d.lineIndex === i);
    if (diffForIndex && diffForIndex.action != null) {
      if (diffForIndex.action === 'accepted_textract') {
        result.push(diffForIndex.textractValue || words[i]);
      } else if (diffForIndex.action === 'accepted_native') {
        result.push(diffForIndex.nativeValue || words[i]);
      } else if (diffForIndex.action === 'edited' && diffForIndex.correctedValue != null) {
        result.push(diffForIndex.correctedValue);
      } else if (diffForIndex.action === 'rejected') {
        // keep native
        result.push(words[i]);
      } else {
        result.push(words[i]);
      }
    } else {
      result.push(words[i]);
    }
    i++;
  }
  return result.join(' ');
}

export default function ReviewTask({ taskId, reviewerId, onComplete }: ReviewTaskProps) {
  const [task, setTask] = useState<A2ITaskDetail | null>(null);
  const [diffItems, setDiffItems] = useState<DiffItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [comment, setComment] = useState('');

  useEffect(() => {
    setLoading(true);
    setImgError(false);
    fetchA2ITaskDetail(taskId).then((detail) => {
      setTask(detail);
      setDiffItems(detail?.diffItems?.map((d) => ({ ...d, action: undefined })) ?? []);
      setLoading(false);
    });
  }, [taskId]);

  const handleDiffAction = useCallback((id: string, action: DiffAction, correctedValue?: string) => {
    setDiffItems((prev) =>
      prev.map((d) =>
        d.id === id ? { ...d, action, correctedValue: correctedValue ?? d.correctedValue } : d
      )
    );
  }, []);

  async function handleAcceptAll() {
    setDiffItems((prev) => prev.map((d) => ({ ...d, action: 'accepted_textract' as DiffAction })));
  }

  async function handleAcceptAllNative() {
    setDiffItems((prev) => prev.map((d) => ({ ...d, action: 'accepted_native' as DiffAction })));
  }

  async function handleSubmit() {
    if (!task) return;
    setSubmitting(true);
    try {
      const correctedText = assembleCorrection(task, diffItems);
      await submitA2ICorrection(taskId, correctedText, reviewerId, comment || undefined);
      onComplete();
    } catch (err) {
      console.error('Submit correction failed:', err);
      alert('Failed to submit correction. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto mb-3" />
          Loading task…
        </div>
      </div>
    );
  }

  if (!task) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        Task not found.
      </div>
    );
  }

  const unresolvedCount = diffItems.filter((d) => d.action == null).length;
  const imgUrl = screenshotUrl(task.documentId, task.pageNumber);

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-800">
            Page {task.pageNumber} Review
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {task.triggerReason}
            {task.confidenceScore != null && (
              <span className="ml-2 text-gray-400">· Conf: {task.confidenceScore.toFixed(1)}%</span>
            )}
          </p>
        </div>
        <span className={`px-2 py-1 rounded text-xs font-medium ${
          task.status === 'completed' ? 'bg-green-100 text-green-700' :
          task.status === 'assigned' ? 'bg-blue-100 text-blue-700' :
          'bg-yellow-100 text-yellow-700'
        }`}>
          {task.status.replace('_', ' ')}
        </span>
      </div>

      {/* Three-column layout */}
      <div className="grid grid-cols-3 gap-3 min-h-64">
        {/* Column 1: Screenshot */}
        <div className="border border-gray-200 rounded-lg p-2 bg-gray-50">
          <p className="text-xs font-medium text-gray-500 mb-2">Page Screenshot</p>
          {imgError ? (
            <div className="flex items-center justify-center h-40 text-gray-400 text-xs">
              Screenshot not available
            </div>
          ) : (
            <img
              src={imgUrl}
              alt={`Page ${task.pageNumber} screenshot`}
              className="w-full rounded border border-gray-200"
              onError={() => setImgError(true)}
            />
          )}
        </div>

        {/* Column 2: Native PDF text */}
        <div className="border border-gray-200 rounded-lg p-3 bg-white overflow-auto max-h-80">
          <p className="text-xs font-medium text-green-700 mb-2">Native PDF</p>
          {task.nativeTextSnapshot ? (
            <pre className="text-xs text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
              {task.nativeTextSnapshot}
            </pre>
          ) : (
            <p className="text-xs text-gray-400 italic">No native text available.</p>
          )}
        </div>

        {/* Column 3: Textract text with highlights */}
        <div className="border border-gray-200 rounded-lg p-3 bg-white overflow-auto max-h-80">
          <p className="text-xs font-medium text-red-600 mb-2">Textract (differences highlighted)</p>
          {task.originalTextractText ? (
            <pre className="text-xs text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
              {highlightDiffs(task.originalTextractText, diffItems)}
            </pre>
          ) : (
            <p className="text-xs text-gray-400 italic">No Textract text available.</p>
          )}
        </div>
      </div>

      {/* DiffViewer */}
      <div className="border border-gray-200 rounded-lg p-4 bg-white">
        <DiffViewer diffItems={diffItems} onAction={handleDiffAction} />
      </div>

      {/* Comment + Submit */}
      <div className="border border-gray-200 rounded-lg p-4 bg-white">
        <div className="mb-3">
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Reviewer Comment (optional)
          </label>
          <textarea
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
            rows={2}
            placeholder="Add a note about this review…"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            {submitting ? 'Submitting…' : 'Submit Correction'}
          </button>
          <button
            onClick={handleAcceptAll}
            className="px-4 py-2 bg-blue-50 text-blue-700 text-sm font-medium rounded hover:bg-blue-100 border border-blue-200"
          >
            Accept All Textract
          </button>
          <button
            onClick={handleAcceptAllNative}
            className="px-4 py-2 bg-green-50 text-green-700 text-sm font-medium rounded hover:bg-green-100 border border-green-200"
          >
            Accept All Native
          </button>
          {unresolvedCount > 0 && (
            <span className="text-xs text-amber-600 font-medium ml-auto">
              {unresolvedCount} item{unresolvedCount !== 1 ? 's' : ''} unresolved
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
