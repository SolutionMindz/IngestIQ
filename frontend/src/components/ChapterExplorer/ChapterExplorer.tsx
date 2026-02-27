import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import type { DocumentStructure, Chapter, ContentBlock } from '../../types/structure';
import type { PageAccuracyItem } from '../../api';
import {
  fetchStructure,
  fetchPageAccuracy,
  fetchPageValidation,
  fetchPageComparisonSummary,
  postPageValidation,
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
  return 'bg-red-500';
}

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

function renderPageContent(
  chapter: Chapter | null,
  failedMessage: string,
  otherChapter: Chapter | null
) {
  if (!chapter) return <p className="text-slate-500">{failedMessage}</p>;
  const otherSet = getOtherSideContentSet(otherChapter);
  return (
    <div className="space-y-2 text-sm prose prose-slate max-w-none prose-p:my-1 prose-pre:my-1 prose-ul:my-1 prose-ol:my-1">
      {chapter.content_blocks.map((block: ContentBlock) => {
        const normalized = normalizeForDiff(block.content || '');
        const onlyInThisColumn = normalized && !otherSet.has(normalized);
        return (
          <div
            key={block.id}
            className={`border-l-2 pl-2 py-0.5 ${onlyInThisColumn ? 'border-amber-400 bg-amber-50' : 'border-slate-200'}`}
          >
            <div className="markdown-preview text-slate-800">
              <ReactMarkdown>
                {block.type === 'table'
                  ? `\`\`\`\n${block.content ?? ''}\n\`\`\``
                  : (block.content ?? '')}
              </ReactMarkdown>
            </div>
            {block.wordCount != null && (
              <span className="text-xs text-slate-400">({block.wordCount} words)</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function ChapterExplorer({ documentId }: ChapterExplorerProps) {
  const [pdfStructure, setPdfStructure] = useState<DocumentStructure | null>(null);
  const [textractStructure, setTextractStructure] = useState<DocumentStructure | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [pageAccuracyList, setPageAccuracyList] = useState<PageAccuracyItem[]>([]);
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

  if (!documentId) {
    return (
      <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">3. Chapter Explorer</h2>
        <p className="text-slate-500">Select a document to compare Native PDF vs Textract by page.</p>
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
        <p className="text-slate-500">No PDF or Textract extraction yet. Upload a PDF and wait for processing.</p>
      </section>
    );
  }

  return (
    <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
      <h2 className="text-lg font-semibold text-slate-800 mb-4">3. Chapter Explorer</h2>
      <div className="grid grid-cols-1 lg:grid-cols-[200px_1fr] gap-3 sm:gap-4 min-h-0">
        {/* Page navigation panel (hierarchy: page numbers only) */}
        <div className="border border-slate-200 rounded overflow-auto max-h-[320px] sm:max-h-[420px] min-h-0 bg-slate-50">
          <div className="p-2 text-xs font-semibold text-slate-500 uppercase">Pages</div>
          {pages.map((pageNum) => {
            const acc = accuracyForPage(pageNum);
            const status = statusForPage(pageNum);
            const isSelected = selectedPage === pageNum;
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
                {acc != null && (
                  <span className="text-xs text-slate-500 ml-auto">{acc.accuracyPct.toFixed(1)}%</span>
                )}
              </button>
            );
          })}
          {pages.length === 0 && (
            <p className="p-2 text-sm text-slate-500">No pages</p>
          )}
        </div>

        {/* Comparison section: two columns with full content */}
        <div className="min-w-0 flex flex-col gap-4">
          {selectedPage != null ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border border-slate-200 rounded overflow-hidden min-h-0">
                <div className="p-3 sm:p-4 bg-slate-50 border-r border-slate-200 overflow-auto max-h-[400px] min-h-[200px]">
                  <div className="text-xs font-semibold text-slate-500 uppercase mb-2">Native PDF (Left)</div>
                  {renderPageContent(
                    nativeChapter,
                    'Native extraction failed for this page.',
                    textractChapter
                  )}
                </div>
                <div className="p-3 sm:p-4 bg-slate-50 overflow-auto max-h-[400px] min-h-[200px]">
                  <div className="text-xs font-semibold text-slate-500 uppercase mb-2">Textract (Right)</div>
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
                      <div>Textract confidence (avg): {pageSummary.confidenceAvgTextract}%</div>
                    )}
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
              Select a page from the list to view Native vs Textract comparison.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
