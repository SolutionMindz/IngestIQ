import { useEffect, useState, useCallback, useRef } from 'react';
import type { A2ITaskDetail, DiffItem, DiffAction } from '../../types/a2i';
import { fetchA2ITaskDetail, submitA2ICorrection, screenshotUrl } from '../../api';
import DiffViewer from './DiffViewer';

interface ReviewTaskProps {
  taskId: string;
  reviewerId: string;
  onComplete: () => void;
}

interface PopupState {
  diffItem: DiffItem;
  sentence: string;
}

/** Returns the sentence in `text` that contains the word at position `wordIndex` (0-based). */
function extractSentence(text: string, wordIndex: number): string {
  const tokens = text.split(/(\s+)/);
  let wIdx = 0;
  let charPos = 0;
  let targetCharStart = 0;

  for (const tok of tokens) {
    if (tok.length > 0 && !/^\s+$/.test(tok)) {
      if (wIdx === wordIndex) {
        targetCharStart = charPos;
        break;
      }
      wIdx++;
    }
    charPos += tok.length;
  }

  // Walk backwards to sentence start
  let sentStart = 0;
  for (let i = targetCharStart - 1; i >= 0; i--) {
    if (/[.!?\n]/.test(text[i])) {
      sentStart = i + 1;
      break;
    }
  }

  // Walk forwards to sentence end
  let sentEnd = text.length;
  for (let i = targetCharStart; i < text.length; i++) {
    if (/[.!?\n]/.test(text[i])) {
      sentEnd = i + 1;
      break;
    }
  }

  return text.slice(sentStart, sentEnd).trim();
}

function highlightDiffs(
  text: string,
  diffItems: DiffItem[],
  onWordClick: (item: DiffItem, wordIndex: number) => void,
): React.ReactNode[] {
  if (!text || diffItems.length === 0) return [text];

  // Primary: map by lineIndex; secondary: map by textract word value (lowercased)
  const diffByIndex = new Map<number, DiffItem>();
  const diffByValue = new Map<string, DiffItem>();
  for (const d of diffItems) {
    if (d.lineIndex != null) diffByIndex.set(d.lineIndex, d);
    if (d.textractValue) diffByValue.set(d.textractValue.toLowerCase(), d);
  }

  const tokens = text.split(/(\s+)/);
  let wordIndex = 0;

  return tokens.map((tok, i) => {
    if (tok.length === 0 || /^\s+$/.test(tok)) return tok;

    const idx = wordIndex++;
    const diffItem = diffByIndex.get(idx) ?? diffByValue.get(tok.trim().toLowerCase());

    if (diffItem) {
      return (
        <mark
          key={i}
          className="bg-red-200 text-red-900 rounded px-0.5 cursor-pointer hover:bg-red-300 transition-colors"
          onClick={() => onWordClick(diffItem, idx)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onWordClick(diffItem, idx); }}
          title="Click to review this difference"
        >
          {tok}
        </mark>
      );
    }
    return tok;
  });
}

function assembleCorrection(task: A2ITaskDetail, diffItems: DiffItem[]): string {
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

  // Column height sync (Task 1)
  const screenshotContainerRef = useRef<HTMLDivElement>(null);
  const [textColHeight, setTextColHeight] = useState<number | undefined>(undefined);

  const updateColHeight = useCallback(() => {
    if (screenshotContainerRef.current) {
      setTextColHeight(screenshotContainerRef.current.clientHeight);
    }
  }, []);

  // Popup state (Task 2)
  const [popup, setPopup] = useState<PopupState | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editValue, setEditValue] = useState('');

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

  const handleHighlightClick = useCallback((item: DiffItem, wordIndex: number) => {
    if (!task) return;
    const sentence = extractSentence(task.originalTextractText ?? '', wordIndex);
    setPopup({ diffItem: item, sentence });
    setEditMode(false);
    setEditValue(item.textractValue || item.nativeValue || '');
  }, [task]);

  const closePopup = useCallback(() => setPopup(null), []);

  const handlePopupAccept = useCallback(() => {
    if (!popup) return;
    handleDiffAction(popup.diffItem.id, 'accepted_textract');
    setPopup(null);
  }, [popup, handleDiffAction]);

  const handlePopupSkip = useCallback(() => {
    if (!popup) return;
    handleDiffAction(popup.diffItem.id, 'rejected');
    setPopup(null);
  }, [popup, handleDiffAction]);

  const handlePopupSave = useCallback(() => {
    if (!popup) return;
    handleDiffAction(popup.diffItem.id, 'edited', editValue);
    setPopup(null);
  }, [popup, editValue, handleDiffAction]);

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

      {/* Three-column layout — heights matched to screenshot column */}
      <div className="grid grid-cols-3 gap-3 items-start">
        {/* Column 1: Screenshot — drives row height */}
        <div
          ref={screenshotContainerRef}
          className="border border-gray-200 rounded-lg p-2 bg-gray-50"
        >
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
              onLoad={updateColHeight}
              onError={() => { setImgError(true); updateColHeight(); }}
            />
          )}
        </div>

        {/* Column 2: PaddleOCR text */}
        <div
          className="border border-gray-200 rounded-lg p-3 bg-white flex flex-col"
          style={textColHeight ? { height: textColHeight } : { minHeight: '20rem' }}
        >
          <p className="text-xs font-medium text-green-700 mb-2 shrink-0">PaddleOCR</p>
          <div className="flex-1 min-h-0 overflow-y-auto">
            {task.nativeTextSnapshot ? (
              <pre className="text-xs text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
                {task.nativeTextSnapshot}
              </pre>
            ) : (
              <p className="text-xs text-gray-400 italic">No PaddleOCR text available.</p>
            )}
          </div>
        </div>

        {/* Column 3: Textract text with clickable highlights */}
        <div
          className="border border-gray-200 rounded-lg p-3 bg-white flex flex-col"
          style={textColHeight ? { height: textColHeight } : { minHeight: '20rem' }}
        >
          <p className="text-xs font-medium text-red-600 mb-2 shrink-0">
            Textract (differences highlighted
            {diffItems.length > 0 && (
              <span className="font-normal text-gray-400"> — click to review</span>
            )}
            )
          </p>
          <div className="flex-1 min-h-0 overflow-y-auto">
            {task.originalTextractText ? (
              <pre className="text-xs text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
                {highlightDiffs(task.originalTextractText, diffItems, handleHighlightClick)}
              </pre>
            ) : (
              <p className="text-xs text-gray-400 italic">No Textract text available.</p>
            )}
          </div>
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
            Accept All PaddleOCR
          </button>
          {unresolvedCount > 0 && (
            <span className="text-xs text-amber-600 font-medium ml-auto">
              {unresolvedCount} item{unresolvedCount !== 1 ? 's' : ''} unresolved
            </span>
          )}
        </div>
      </div>

      {/* Word difference popup */}
      {popup && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={(e) => { if (e.target === e.currentTarget) closePopup(); }}
        >
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
            {/* Title bar */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-gray-800">Word difference</h3>
              <button
                onClick={closePopup}
                className="text-gray-400 hover:text-gray-600 transition-colors"
                aria-label="Close"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Body */}
            <div className="px-5 py-4 space-y-4">
              {/* Full sentence */}
              <p className="text-sm text-gray-700 leading-relaxed">{popup.sentence}</p>

              {/* PaddleOCR vs Textract comparison */}
              <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 space-y-1.5">
                <div className="flex items-start gap-2 text-xs">
                  <span className="text-gray-500 font-medium w-16 shrink-0">PaddleOCR:</span>
                  <span className="text-green-700 font-mono">{popup.diffItem.nativeValue || '—'}</span>
                </div>
                <div className="flex items-start gap-2 text-xs">
                  <span className="text-gray-500 font-medium w-16 shrink-0">Textract:</span>
                  <span className="text-red-600 font-mono">{popup.diffItem.textractValue || '—'}</span>
                </div>
              </div>

              {/* Inline edit field */}
              {editMode && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Corrected value</label>
                  <input
                    type="text"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    className="w-full border border-indigo-400 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handlePopupSave();
                      if (e.key === 'Escape') setEditMode(false);
                    }}
                  />
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-2 px-5 py-3 border-t border-gray-200 bg-gray-50">
              {editMode ? (
                <>
                  <button
                    onClick={handlePopupSave}
                    className="px-4 py-1.5 bg-indigo-600 text-white text-xs font-medium rounded hover:bg-indigo-700"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditMode(false)}
                    className="px-4 py-1.5 bg-gray-200 text-gray-700 text-xs font-medium rounded hover:bg-gray-300"
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={handlePopupAccept}
                    className="px-4 py-1.5 bg-blue-600 text-white text-xs font-medium rounded hover:bg-blue-700"
                  >
                    Accept (Textract)
                  </button>
                  <button
                    onClick={handlePopupSkip}
                    className="px-4 py-1.5 bg-gray-200 text-gray-600 text-xs font-medium rounded hover:bg-gray-300"
                  >
                    Skip
                  </button>
                  <button
                    onClick={() => setEditMode(true)}
                    className="px-4 py-1.5 bg-indigo-100 text-indigo-700 text-xs font-medium rounded hover:bg-indigo-200"
                  >
                    Edit
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
