import React, { useState, useEffect } from 'react';
import type { DocumentStructure, Chapter, ContentBlock } from '../../types/structure';
import type { PageAccuracyItem } from '../../api';
import type { A2ITask } from '../../types/a2i';
import {
  fetchStructure,
  fetchPageAccuracy,
  fetchPageValidation,
  fetchPageComparisonSummary,
  postPageValidation,
  fetchA2ITasks,
  triggerA2IReview,
} from '../../api';

const PAGE_STATUS_OPTIONS = [
  'verified',
  'needs_review',
  'layout_issue',
  'table_issue',
  'ocr_issue',
  'missing_content',
] as const;

interface ChapterExplorerProps {
  documentId: string | null;
}

function getStatusColor(status: PageAccuracyItem['status']): string {
  if (status === 'OK') return 'bg-green-500';
  if (status === 'WARNING') return 'bg-amber-500';
  if (status === 'FORMULA') return 'bg-blue-500';
  if (status === 'IMAGE') return 'bg-purple-500';
  if (status === 'SPARSE') return 'bg-gray-400';
  return 'bg-red-500';
}

const STATUS_LABEL: Record<string, string | null> = {
  OK: null,
  WARNING: null,
  ERROR: null,
  FORMULA: 'formula page',
  IMAGE: 'image page',
  SPARSE: 'sparse page',
};

function getChapterForPage(structure: DocumentStructure | null, pageNumber: number): Chapter | null {
  if (!structure?.chapters) return null;
  const heading = `Page ${pageNumber}`;
  return structure.chapters.find((ch) => ch.heading === heading) ?? null;
}

function normalizeForDiff(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, ' ');
}

function getOtherSideContentSet(chapter: Chapter | null): Set<string> {
  if (!chapter?.content_blocks) return new Set();
  const set = new Set<string>();
  for (const b of chapter.content_blocks) {
    const n = normalizeForDiff(b.content || '');
    if (n) set.add(n);
  }
  return set;
}

// Human-readable label for each block type (matches reference design)
const BLOCK_TYPE_LABEL: Record<string, string> = {
  title:      'Heading',
  paragraph:  'Paragraph',
  text:       'Paragraph',
  list_item:  'List',
  code_block: 'Code',
  code:       'Code',
  table:      'Table',
  formula:    'Formula',
  image:      'Figure',
};

// Badge color variant per type
const BADGE_COLOR: Record<string, string> = {
  title:      'bg-slate-100 text-slate-600',
  paragraph:  'bg-slate-100 text-slate-600',
  text:       'bg-slate-100 text-slate-600',
  list_item:  'bg-blue-50 text-blue-600',
  code_block: 'bg-slate-100 text-slate-600',
  code:       'bg-slate-100 text-slate-600',
  table:      'bg-violet-50 text-violet-600',
  formula:    'bg-slate-100 text-slate-600',
  image:      'bg-slate-100 text-slate-600',
};

function TypeBadge({ type }: { type: string }) {
  const label = BLOCK_TYPE_LABEL[type] ?? type;
  const color = BADGE_COLOR[type] ?? 'bg-slate-100 text-slate-600';
  return (
    <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full ${color}`}>
      {label}
    </span>
  );
}

function renderBlockContent(block: ContentBlock): React.ReactNode {
  if (block.type === 'title') {
    return <p className="font-bold text-slate-900 text-lg leading-snug mt-1">{block.content}</p>;
  }
  if (block.type === 'list_item') {
    return (
      <div className="border-l-2 border-blue-300 pl-3 mt-1">
        <p className="text-slate-800">{block.content}</p>
      </div>
    );
  }
  if (block.type === 'code_block' || block.type === 'code') {
    return (
      <pre className="mt-1 text-xs font-mono text-slate-800 bg-slate-50 border border-slate-200 rounded p-2 whitespace-pre-wrap overflow-x-auto">
        {block.content}
      </pre>
    );
  }
  if (block.type === 'formula') {
    return <p className="mt-1 text-slate-500 italic">[Formula]</p>;
  }
  if (block.type === 'table') {
    return <OcrTable content={block.content} />;
  }
  if (block.type === 'image') {
    const hasAltText = block.content && block.content !== '[figure]' && block.content !== '[Figure]';
    return hasAltText
      ? <p className="mt-1 text-slate-500 italic text-sm">[Figure] {block.content}</p>
      : <p className="mt-1 text-slate-400 italic">[Figure]</p>;
  }
  // paragraph / text
  return <p className="mt-1 text-slate-800 leading-relaxed">{block.content}</p>;
}

/** Render OCR table content as an HTML table.
 *  Content is tab/pipe separated rows, or falls back to plain text. */
function OcrTable({ content }: { content: string }) {
  const lines = (content ?? '').split('\n').filter((l) => l.trim());
  // Try pipe-separated markdown table
  const rows = lines.map((line) =>
    line.replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
  );
  const hasCols = rows.length > 0 && rows[0].length > 1;
  if (!hasCols) {
    return <pre className="mt-1 text-xs font-mono text-slate-700 whitespace-pre-wrap">{content}</pre>;
  }
  const [header, _sep, ...body] = rows;
  const dataRows = body.length > 0 ? body : rows.slice(1);
  return (
    <div className="mt-1 overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        {header && (
          <thead>
            <tr>
              {header.map((cell, i) => (
                <th key={i} className="text-left px-3 py-2 text-slate-600 font-medium border-b border-slate-200">
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {dataRows.map((row, ri) => (
            <tr key={ri} className="border-b border-slate-100 last:border-0">
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-2 text-slate-700 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderBlock(block: ContentBlock, highlighted: boolean) {
  return (
    <div
      key={block.id}
      className={`pb-3 mb-1 border-b border-slate-100 last:border-0 ${highlighted ? 'bg-amber-50 -mx-1 px-1 rounded' : ''}`}
    >
      <TypeBadge type={block.type} />
      {renderBlockContent(block)}
    </div>
  );
}

function renderPageContent(
  chapter: Chapter | null,
  failedMessage: string,
  otherChapter: Chapter | null
) {
  if (!chapter) return <p className="text-slate-500">{failedMessage}</p>;
  const otherSet = getOtherSideContentSet(otherChapter);
  return (
    <div>
      <div className="text-[10px] font-semibold tracking-widest text-slate-400 uppercase mb-3">
        Extracted Content
      </div>
      <div className="space-y-0">
        {chapter.content_blocks.map((block: ContentBlock) => {
          const normalized = normalizeForDiff(block.content || '');
          const onlyInThisColumn = !!(normalized && !otherSet.has(normalized));
          return renderBlock(block, onlyInThisColumn);
        })}
      </div>
    </div>
  );
}

function A2ITaskPanel({
  task,
  onTrigger,
  triggering,
  accuracyPct,
}: {
  task: A2ITask | null;
  onTrigger: () => void;
  triggering: boolean;
  accuracyPct: number | null;
}) {
  if (task) {
    if (task.status === 'completed') {
      return (
        <div className="flex items-center gap-2 p-2 bg-green-50 border border-green-200 rounded text-sm">
          <span className="w-2 h-2 rounded-full bg-green-500 shrink-0" />
          <div>
            <span className="font-medium text-green-800">Human Verified</span>
            {task.reviewerId && <span className="text-green-700 ml-1">by {task.reviewerId}</span>}
            {task.reviewTimestamp && (
              <span className="text-green-600 ml-1">· {new Date(task.reviewTimestamp).toLocaleString()}</span>
            )}
          </div>
        </div>
      );
    }
    if (task.status === 'under_review') {
      return (
        <div className="flex items-center gap-2 p-2 bg-blue-50 border border-blue-200 rounded text-sm">
          <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0 animate-pulse" />
          <span className="text-blue-800 font-medium">Human Review In Progress</span>
          {task.humanLoopName && <span className="text-blue-600 text-xs">({task.humanLoopName})</span>}
        </div>
      );
    }
    if (task.status === 'pending') {
      return (
        <div className="flex items-center gap-2 p-2 bg-amber-50 border border-amber-200 rounded text-sm">
          <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
          <span className="text-amber-800 font-medium">Pending Review</span>
          <span className="text-amber-600 text-xs ml-auto">{task.triggerReason}</span>
        </div>
      );
    }
    if (task.status === 'failed') {
      return (
        <div className="flex items-center gap-2 p-2 bg-red-50 border border-red-200 rounded text-sm">
          <span className="w-2 h-2 rounded-full bg-red-500 shrink-0" />
          <span className="text-red-800 font-medium">Review Failed</span>
        </div>
      );
    }
    return null;
  }

  if (accuracyPct != null && accuracyPct < 98) {
    return (
      <button
        type="button"
        disabled={triggering}
        onClick={onTrigger}
        className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
      >
        {triggering ? 'Sending to Review…' : 'Send to Human Review'}
      </button>
    );
  }

  return null;
}

export default function ChapterExplorer({ documentId }: ChapterExplorerProps) {
  const [pdfStructure, setPdfStructure] = useState<DocumentStructure | null>(null);
  const [textractStructure, setTextractStructure] = useState<DocumentStructure | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [pageAccuracyList, setPageAccuracyList] = useState<PageAccuracyItem[]>([]);
  const [a2iTasks, setA2ITasks] = useState<A2ITask[]>([]);
  const [triggeringA2I, setTriggeringA2I] = useState(false);
  const [pageValidation, setPageValidation] = useState<{
    reviewer: string;
    status: string;
    comment: string | null;
    timestamp: string | null;
  } | null>(null);
  const [pageSummary, setPageSummary] = useState<{
    wordCountNative: number;
    wordCountTextract: number;
    blockCountNative: number;
    blockCountTextract: number;
    tableCountNative: number;
    tableCountTextract: number;
    missingBlockCount: number;
    accuracyScore: number | null;
    validationStatus: string | null;
    confidenceAvgTextract: number | null;
  } | null>(null);
  const [pageComment, setPageComment] = useState('');

  useEffect(() => {
    if (!documentId) {
      setPdfStructure(null);
      setTextractStructure(null);
      setSelectedPage(null);
      setPageAccuracyList([]);
      setA2ITasks([]);
      setPageValidation(null);
      setPageSummary(null);
      return;
    }
    setLoading(true);
    Promise.all([
      fetchStructure(documentId, 'pdf'),
      fetchStructure(documentId, 'textract'),
    ]).then(([pdf, textract]) => {
      setPdfStructure(pdf ?? null);
      setTextractStructure(textract ?? null);
      setLoading(false);
    });
  }, [documentId]);

  useEffect(() => {
    if (!documentId) return;
    fetchPageAccuracy(documentId).then(setPageAccuracyList).catch(() => setPageAccuracyList([]));
    fetchA2ITasks(documentId).then(setA2ITasks).catch(() => setA2ITasks([]));
  }, [documentId]);

  const pageCount =
    pdfStructure?.pageCount ??
    pdfStructure?.chapters?.length ??
    textractStructure?.pageCount ??
    textractStructure?.chapters?.length ??
    (pageAccuracyList.length || 0);

  const pages = Array.from({ length: Math.max(0, pageCount) }, (_, i) => i + 1);

  useEffect(() => {
    if (!documentId || selectedPage == null) {
      setPageValidation(null);
      setPageSummary(null);
      return;
    }
    Promise.all([
      fetchPageValidation(documentId, selectedPage),
      fetchPageComparisonSummary(documentId, selectedPage).catch(() => null),
    ]).then(([validation, summary]) => {
      setPageValidation(validation ?? null);
      setPageSummary(summary ?? null);
    });
  }, [documentId, selectedPage]);

  const nativeChapter = getChapterForPage(pdfStructure, selectedPage ?? 0);
  const textractChapter = getChapterForPage(textractStructure, selectedPage ?? 0);

  const accuracyForPage = (pageNum: number) =>
    pageAccuracyList.find((a) => a.pageNumber === pageNum);
  const statusForPage = (pageNum: number) => accuracyForPage(pageNum)?.status ?? 'ERROR';
  const a2iTaskByPage = Object.fromEntries(a2iTasks.map((t) => [t.pageNumber, t]));

  const handleTriggerA2I = async () => {
    if (!documentId || selectedPage == null) return;
    setTriggeringA2I(true);
    try {
      const task = await triggerA2IReview(documentId, selectedPage);
      setA2ITasks((prev) => [...prev.filter((t) => t.pageNumber !== selectedPage), task]);
    } catch (err) {
      console.error('Failed to trigger A2I review:', err);
    } finally {
      setTriggeringA2I(false);
    }
  };

  if (!documentId) {
    return (
      <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">3. Chapter Explorer</h2>
        <p className="text-slate-500">Select a document to compare PaddleOCR vs AWS Textract by page.</p>
      </section>
    );
  }

  if (loading) {
    return (
      <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">3. Chapter Explorer</h2>
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-slate-800" />
        </div>
      </section>
    );
  }

  const hasAnyStructure = pdfStructure ?? textractStructure;
  if (!hasAnyStructure) {
    return (
      <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">3. Chapter Explorer</h2>
        <p className="text-slate-500">No PaddleOCR or Textract extraction yet. Upload a PDF and wait for processing.</p>
      </section>
    );
  }

  return (
    <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
      <h2 className="text-lg font-semibold text-slate-800 mb-4">3. Chapter Explorer</h2>
      <div className="grid grid-cols-1 lg:grid-cols-[200px_1fr] gap-3 sm:gap-4 min-h-0">
        {/* Page navigation panel */}
        <div className="border border-slate-200 rounded overflow-auto max-h-[320px] sm:max-h-[420px] min-h-0 bg-slate-50">
          <div className="p-2 text-xs font-semibold text-slate-500 uppercase">Pages</div>
          {pages.map((pageNum) => {
            const acc = accuracyForPage(pageNum);
            const status = statusForPage(pageNum);
            const isSelected = selectedPage === pageNum;
            const a2iTask = a2iTaskByPage[pageNum];
            return (
              <button
                key={pageNum}
                type="button"
                onClick={() => setSelectedPage(pageNum)}
                className={`w-full flex items-center gap-2 py-2 px-2 text-left rounded border-b border-slate-100 last:border-b-0 ${
                  isSelected ? 'bg-slate-200' : 'hover:bg-slate-100'
                }`}
              >
                <span
                  className={`shrink-0 w-2 h-2 rounded-full ${getStatusColor(status)}`}
                  title={status}
                  aria-hidden
                />
                <span className="font-medium text-slate-800">Page {pageNum}</span>
                {STATUS_LABEL[status] && (
                  <span className="text-[10px] text-slate-400 italic">{STATUS_LABEL[status]}</span>
                )}
                {acc != null && (
                  <span className="text-xs text-slate-500 ml-auto">{acc.accuracyPct.toFixed(1)}%</span>
                )}
                {/* A2I dot indicator */}
                {a2iTask && (
                  <span
                    className={`shrink-0 w-1.5 h-1.5 rounded-full ${
                      a2iTask.status === 'completed' ? 'bg-green-400' :
                      a2iTask.status === 'under_review' ? 'bg-blue-400' :
                      a2iTask.status === 'failed' ? 'bg-red-400' : 'bg-amber-400'
                    }`}
                    title={`A2I: ${a2iTask.status}`}
                    aria-hidden
                  />
                )}
              </button>
            );
          })}
          {pages.length === 0 && (
            <p className="p-2 text-sm text-slate-500">No pages</p>
          )}
        </div>

        {/* Comparison section */}
        <div className="min-w-0 flex flex-col gap-4">
          {selectedPage != null ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border border-slate-200 rounded overflow-hidden min-h-0">
                <div className="p-4 bg-white border-r border-slate-200 overflow-auto max-h-[600px] min-h-[200px]">
                  {renderPageContent(
                    nativeChapter,
                    'PaddleOCR extraction failed for this page.',
                    textractChapter
                  )}
                </div>
                <div className="p-4 bg-white overflow-auto max-h-[600px] min-h-[200px]">
                  {renderPageContent(
                    textractChapter,
                    'Textract extraction failed for this page.',
                    nativeChapter
                  )}
                </div>
              </div>

              {/* Page comparison summary */}
              {pageSummary && (
                <div className="border border-slate-200 rounded p-3 sm:p-4 bg-slate-50 text-sm">
                  <div className="text-xs font-semibold text-slate-500 uppercase mb-2">Page {selectedPage} comparison</div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div>Word count: {pageSummary.wordCountNative} vs {pageSummary.wordCountTextract}</div>
                    <div>Blocks: {pageSummary.blockCountNative} vs {pageSummary.blockCountTextract}</div>
                    <div>Tables: {pageSummary.tableCountNative} vs {pageSummary.tableCountTextract}</div>
                    <div>Missing blocks: {pageSummary.missingBlockCount}</div>
                    {pageSummary.accuracyScore != null && (
                      <div>Page accuracy: {pageSummary.accuracyScore}%</div>
                    )}
                    {pageSummary.confidenceAvgTextract != null && (
                      <div>OCR confidence (avg): {pageSummary.confidenceAvgTextract}%</div>
                    )}
                  </div>

                  {/* A2I task status for this page */}
                  <div className="mt-3 pt-3 border-t border-slate-200">
                    <div className="text-xs font-semibold text-slate-500 uppercase mb-2">Human Review</div>
                    <A2ITaskPanel
                      task={a2iTaskByPage[selectedPage] ?? null}
                      onTrigger={handleTriggerA2I}
                      triggering={triggeringA2I}
                      accuracyPct={accuracyForPage(selectedPage)?.accuracyPct ?? null}
                    />
                  </div>
                </div>
              )}

              {/* Page actions */}
              <div className="border border-slate-200 rounded p-3 sm:p-4">
                <div className="text-xs font-semibold text-slate-500 uppercase mb-2">Page actions</div>
                <div className="flex flex-wrap gap-2 mb-3">
                  <button
                    type="button"
                    onClick={() =>
                      postPageValidation(documentId, selectedPage, { status: 'verified' }).then(() =>
                        fetchPageValidation(documentId, selectedPage).then(setPageValidation)
                      )
                    }
                    className="px-3 py-1.5 bg-green-600 text-white rounded text-sm hover:bg-green-700"
                  >
                    Approve page
                  </button>
                  {PAGE_STATUS_OPTIONS.filter((s) => s !== 'verified').map((status) => (
                    <button
                      key={status}
                      type="button"
                      onClick={() =>
                        postPageValidation(documentId, selectedPage, { status }).then(() =>
                          fetchPageValidation(documentId, selectedPage).then(setPageValidation)
                        )
                      }
                      className={`px-2 py-1 rounded text-sm border ${
                        pageValidation?.status === status
                          ? 'bg-slate-700 text-white border-slate-700'
                          : 'bg-white border-slate-300 hover:bg-slate-100'
                      }`}
                    >
                      {status.replace(/_/g, ' ')}
                    </button>
                  ))}
                </div>
                {pageValidation && (
                  <p className="text-xs text-slate-500 mb-2">
                    Last: {pageValidation.reviewer} — {pageValidation.status}
                    {pageValidation.timestamp ? ` (${new Date(pageValidation.timestamp).toLocaleString()})` : ''}
                  </p>
                )}
                <div className="flex gap-2 items-start">
                  <textarea
                    value={pageComment}
                    onChange={(e) => setPageComment(e.target.value)}
                    placeholder="Add a comment..."
                    className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm min-h-[60px]"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      if (!pageComment.trim()) return;
                      postPageValidation(documentId, selectedPage, { comment: pageComment.trim() }).then(() => {
                        fetchPageValidation(documentId, selectedPage).then(setPageValidation);
                        setPageComment('');
                      });
                    }}
                    className="px-2 py-1 bg-slate-600 text-white rounded text-sm hover:bg-slate-700 shrink-0"
                  >
                    Submit comment
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="border border-slate-200 rounded p-6 text-slate-500 text-center">
              Select a page from the list to view PaddleOCR vs AWS Textract comparison.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
