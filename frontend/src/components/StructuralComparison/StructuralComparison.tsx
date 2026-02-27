import { useState, useEffect, useRef, useCallback } from 'react';
import ReactDiffViewer from 'react-diff-viewer-continued';
import ReactMarkdown from 'react-markdown';
import type { DocumentStructure, ContentBlock } from '../../types/structure';
import type { ComparisonResult, Mismatch } from '../../types/comparison';
import type { PageAccuracyItem } from '../../api';
import { fetchStructure, fetchComparison, fetchPageAccuracy, fetchPageMarkdown, screenshotUrl } from '../../api';

function getPageText(structure: DocumentStructure, pageNumber: number): string {
  const ch = structure.chapters.find((c) => c.heading === `Page ${pageNumber}`);
  if (!ch) return '';
  return ch.content_blocks.map((b) => b.content).join(' ');
}

interface StructuralComparisonProps {
  documentId: string | null;
}

/** Raw text view: render content_blocks as chips (optionally with bbox hint). */
function RawTextChips({ structure, label }: { structure: DocumentStructure; label: string }) {
  return (
    <div className="space-y-3">
      <div className="text-xs font-semibold text-slate-500 uppercase">{label}</div>
      <div className="flex flex-col gap-2">
        {structure.chapters.map((ch) => (
          <div key={ch.chapter_id} className="space-y-1.5">
            <div className="text-sm font-medium text-slate-700">{ch.heading}</div>
            <div className="flex flex-wrap gap-1.5">
              {ch.content_blocks.map((b: ContentBlock) => (
                <span
                  key={b.id}
                  className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-200 text-slate-800 text-sm"
                  title={b.bbox ? `bbox: ${b.bbox.left.toFixed(2)}, ${b.bbox.top.toFixed(2)}` : undefined}
                >
                  {b.content}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const FIRST_MISMATCH_HIGHLIGHT_ID = 'first-mismatch-highlight';

function StructureTree({
  structure,
  mismatches,
  side: _side,
  scrollTargetId,
}: {
  structure: DocumentStructure;
  mismatches: Mismatch[];
  side: 'docx' | 'pdf';
  scrollTargetId?: string;
}) {
  const mismatchBlockIds = new Set(mismatches.flatMap((m) => (m.blockId ? [m.blockId] : [])));
  const mismatchChapterIndices = new Set(mismatches.map((m) => m.chapterIndex).filter((i) => i !== undefined) as number[]);

  // First mismatch in document order (for "see highlights" scroll target)
  let firstMismatchKey: string | null = null;
  for (let idx = 0; idx < structure.chapters.length; idx++) {
    if (mismatchChapterIndices.has(idx)) {
      firstMismatchKey = `chapter-${idx}`;
      break;
    }
    const ch = structure.chapters[idx];
    for (const b of ch.content_blocks) {
      if (mismatchBlockIds.has(b.id)) {
        firstMismatchKey = `block-${b.id}`;
        break;
      }
    }
    if (firstMismatchKey) break;
  }

  return (
    <div className="font-mono text-sm">
      {structure.chapters.map((ch, idx) => {
        const chapterMismatch = mismatchChapterIndices.has(idx);
        const isFirstMismatchChapter = scrollTargetId && firstMismatchKey === `chapter-${idx}`;
        return (
          <div key={ch.chapter_id} className="mb-3">
            <div
              id={isFirstMismatchChapter ? scrollTargetId : undefined}
              className={`font-semibold py-1 px-2 rounded ${chapterMismatch ? 'bg-amber-200' : 'bg-slate-100'}`}
            >
              Ch {idx + 1}: {ch.heading}
            </div>
            <ul className="list-none pl-4 mt-1 space-y-1">
              {ch.content_blocks.map((b) => {
                const isFirstMismatchBlock = scrollTargetId && firstMismatchKey === `block-${b.id}`;
                return (
                  <li
                    key={b.id}
                    id={isFirstMismatchBlock ? scrollTargetId : undefined}
                    className={`py-0.5 px-2 rounded ${mismatchBlockIds.has(b.id) ? 'bg-red-100' : ''}`}
                  >
                    [{b.type}] {b.content.slice(0, 50)}{b.content.length > 50 ? '…' : ''}
                  </li>
                );
              })}
              {ch.sections?.map((sec) => (
                <li key={sec.id} className="pl-2 border-l-2 border-slate-200 mt-1">
                  <div className="font-medium text-slate-700">{sec.heading}</div>
                  {sec.contentBlocks.map((b) => (
                    <div key={b.id} className="text-slate-600 pl-2">[{b.type}] {b.content.slice(0, 40)}…</div>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

export default function StructuralComparison({ documentId }: StructuralComparisonProps) {
  const [docx, setDocx] = useState<DocumentStructure | null>(null);
  const [pdf, setPdf] = useState<DocumentStructure | null>(null);
  const [textract, setTextract] = useState<DocumentStructure | null>(null);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<'tree' | 'raw'>('tree');
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [pageAccuracyList, setPageAccuracyList] = useState<PageAccuracyItem[]>([]);
  const [diffSelection, setDiffSelection] = useState<{ chapterIndex: number } | null>(null);
  const [chapterPage, setChapterPage] = useState(0); // pagination for chapter buttons
  const [syncScroll, setSyncScroll] = useState(false);
  const [pagePreviewMarkdown, setPagePreviewMarkdown] = useState(false);
  const [leftPageMarkdown, setLeftPageMarkdown] = useState<string | null>(null);
  const [rightPageMarkdown, setRightPageMarkdown] = useState<string | null>(null);

  const CHAPTERS_PER_PAGE = 10;
  const leftColRef = useRef<HTMLDivElement>(null);
  const rightColRef = useRef<HTMLDivElement>(null);
  const syncingRef = useRef(false);

  const handleScroll = useCallback(
    (source: 'left' | 'right') => {
      if (!syncScroll || syncingRef.current) return;
      const sourceEl = source === 'left' ? leftColRef.current : rightColRef.current;
      const targetEl = source === 'left' ? rightColRef.current : leftColRef.current;
      if (!sourceEl || !targetEl) return;
      const { scrollTop, scrollHeight, clientHeight } = sourceEl;
      const maxScroll = scrollHeight - clientHeight;
      if (maxScroll <= 0) return;
      const ratio = scrollTop / maxScroll;
      syncingRef.current = true;
      const targetMax = targetEl.scrollHeight - targetEl.clientHeight;
      targetEl.scrollTop = ratio * targetMax;
      requestAnimationFrame(() => {
        syncingRef.current = false;
      });
    },
    [syncScroll]
  );

  useEffect(() => {
    if (!documentId) {
      setDocx(null);
      setPdf(null);
      setTextract(null);
      setComparison(null);
      setPageAccuracyList([]);
      setSelectedPage(null);
      setLeftPageMarkdown(null);
      setRightPageMarkdown(null);
      return;
    }
    setLoading(true);
    Promise.all([
      fetchStructure(documentId, 'docx'),
      fetchStructure(documentId, 'pdf'),
      fetchStructure(documentId, 'textract'),
      fetchComparison(documentId),
      fetchPageAccuracy(documentId).catch(() => []),
    ]).then(([d, p, t, c, acc]) => {
      setDocx(d ?? null);
      setPdf(p ?? null);
      setTextract(t ?? null);
      setComparison(c ?? null);
      setPageAccuracyList(Array.isArray(acc) ? acc : []);
      setLoading(false);
    });
  }, [documentId]);

  // Resolve left/right labels for markdown source (depends on docx, pdf, textract)
  const leftIsPdf = !docx && !!pdf;
  const rightIsPdf = !!docx && !!pdf;
  const rightIsTextract = !docx && !!textract;

  useEffect(() => {
    if (!pagePreviewMarkdown || !documentId || selectedPage == null) {
      setLeftPageMarkdown(null);
      setRightPageMarkdown(null);
      return;
    }
    let cancelled = false;
    const fetches: Promise<void>[] = [];
    if (leftIsPdf) {
      fetches.push(
        fetchPageMarkdown(documentId, selectedPage, 'pdf').then((r) => {
          if (!cancelled && r) setLeftPageMarkdown(r.markdown);
          else if (!cancelled) setLeftPageMarkdown(null);
        }).catch(() => {
          if (!cancelled) setLeftPageMarkdown(null);
        })
      );
    } else {
      setLeftPageMarkdown(null);
    }
    if (rightIsTextract) {
      fetches.push(
        fetchPageMarkdown(documentId, selectedPage, 'textract').then((r) => {
          if (!cancelled && r) setRightPageMarkdown(r.markdown);
          else if (!cancelled) setRightPageMarkdown(null);
        }).catch(() => {
          if (!cancelled) setRightPageMarkdown(null);
        })
      );
    } else if (rightIsPdf) {
      fetches.push(
        fetchPageMarkdown(documentId, selectedPage, 'pdf').then((r) => {
          if (!cancelled && r) setRightPageMarkdown(r.markdown);
          else if (!cancelled) setRightPageMarkdown(null);
        }).catch(() => {
          if (!cancelled) setRightPageMarkdown(null);
        })
      );
    } else {
      setRightPageMarkdown(null);
    }
    return () => { cancelled = true; };
  }, [documentId, selectedPage, pagePreviewMarkdown, leftIsPdf, rightIsPdf, rightIsTextract]);

  if (!documentId) {
    return (
      <section className="bg-white rounded-lg shadow p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">2. Structural Comparison Viewer</h2>
        <p className="text-slate-500">Select a document to compare DOCX vs PDF, or PDF vs AWS Textract.</p>
      </section>
    );
  }

  if (loading) {
    return (
      <section className="bg-white rounded-lg shadow p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">2. Structural Comparison Viewer</h2>
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-slate-800" />
        </div>
      </section>
    );
  }

  // Side-by-side: DOCX vs PDF when both exist; else PDF vs Textract for PDF-only docs
  const left = docx && pdf ? docx : pdf;
  const right = docx && pdf ? pdf : textract;
  const leftLabel = docx && pdf ? 'DOCX' : 'PDF';
  const rightLabel = docx && pdf ? 'PDF' : 'Textract';
  const mismatches = comparison?.mismatches ?? [];
  const pageCount = left?.pageCount ?? left?.chapters?.length ?? right?.chapters?.length ?? 0;
  const selectedPageAccuracy = selectedPage != null ? pageAccuracyList.find((a) => a.pageNumber === selectedPage) : null;

  return (
    <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
      <h2 className="text-lg font-semibold text-slate-800 mb-4">2. Structural Comparison Viewer</h2>
      <div className="mb-4 p-3 bg-slate-100 rounded flex flex-wrap gap-3 sm:gap-4 text-sm items-center">
        {comparison && (
          <>
            <span>Chapters: {comparison.chapterCountMatch ? '✓' : '✗'}</span>
            <span>Headings: {comparison.headingMatch ? '✓' : '✗'}</span>
            <span>Word count: {comparison.wordCountMatch ? '✓' : '✗'} ({comparison.docxWordCount} vs {comparison.pdfWordCount})</span>
            <span className="text-slate-500">({leftLabel} vs {rightLabel})</span>
            {mismatches.length > 0 && (
              <span className="text-amber-700 font-medium">
                {mismatches.length} mismatch{mismatches.length === 1 ? '' : 'es'} —{' '}
                <button
                  type="button"
                  onClick={() => {
                    setViewMode('tree');
                    requestAnimationFrame(() => {
                      setTimeout(() => {
                        document.getElementById(FIRST_MISMATCH_HIGHLIGHT_ID)?.scrollIntoView({
                          behavior: 'smooth',
                          block: 'center',
                        });
                      }, 100);
                    });
                  }}
                  className="underline hover:no-underline focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-1 rounded"
                >
                  see highlights
                </button>
              </span>
            )}
          </>
        )}
        {(left || right) && (
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-slate-600 text-xs uppercase font-medium">View:</span>
            <button
              type="button"
              onClick={() => setViewMode('tree')}
              className={`px-2 py-1 rounded text-sm ${viewMode === 'tree' ? 'bg-slate-700 text-white' : 'bg-slate-200 hover:bg-slate-300'}`}
            >
              Tree
            </button>
            <button
              type="button"
              onClick={() => setViewMode('raw')}
              className={`px-2 py-1 rounded text-sm ${viewMode === 'raw' ? 'bg-slate-700 text-white' : 'bg-slate-200 hover:bg-slate-300'}`}
            >
              Raw text
            </button>
          </div>
        )}
        {viewMode === 'tree' && comparison && (
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={syncScroll}
              onChange={(e) => setSyncScroll(e.target.checked)}
              className="rounded border-slate-300"
            />
            <span className="text-slate-600">Sync scroll</span>
          </label>
        )}
      </div>
      {viewMode === 'raw' && pageCount > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-x-6 gap-y-3 px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg">
          <div className="flex items-center gap-2">
            <label htmlFor="struct-select-page" className="text-sm font-medium text-slate-700 whitespace-nowrap">
              Select page:
            </label>
            <select
              id="struct-select-page"
              value={selectedPage ?? ''}
              onChange={(e) => setSelectedPage(e.target.value ? Number(e.target.value) : null)}
              className="rounded border border-slate-300 px-3 py-1.5 text-sm bg-white min-w-[4rem]"
            >
              <option value="">—</option>
              {Array.from({ length: pageCount }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
          {selectedPage != null && (
            <>
              <span className="hidden sm:inline w-px h-5 bg-slate-200" aria-hidden />
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={pagePreviewMarkdown}
                  onChange={(e) => setPagePreviewMarkdown(e.target.checked)}
                  className="rounded border-slate-300 text-slate-700"
                />
                <span className="text-sm text-slate-700">Preview as Markdown</span>
              </label>
            </>
          )}
        </div>
      )}

      {viewMode === 'raw' && selectedPage != null && left && right && documentId ? (
        <div className="mb-4 border border-slate-200 rounded overflow-hidden">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-3 bg-slate-50 md:items-stretch">
            <div className="flex flex-col min-h-[320px] md:min-h-0">
              <div className="text-xs font-semibold text-slate-500 uppercase mb-2 shrink-0">Screenshot</div>
              <div className="flex-1 min-h-0 overflow-auto flex justify-center bg-white rounded border border-slate-200">
                <img
                  src={screenshotUrl(documentId, selectedPage)}
                  alt={`Page ${selectedPage}`}
                  className="max-w-full max-h-full object-contain"
                />
              </div>
            </div>
            <div className="flex flex-col min-h-[320px] md:min-h-0">
              <div className="text-xs font-semibold text-slate-500 uppercase mb-2 shrink-0">
                {pagePreviewMarkdown && leftPageMarkdown != null ? `${leftLabel} markdown` : `${leftLabel} raw text`}
              </div>
              <div className="flex-1 min-h-0 overflow-auto text-sm text-slate-800 break-words p-2 bg-white rounded border border-slate-200 [&_table]:border [&_table]:border-slate-300 [&_th]:border [&_th]:border-slate-300 [&_td]:border [&_td]:border-slate-300 [&_th]:px-2 [&_td]:px-2">
                {pagePreviewMarkdown && leftIsPdf ? (
                  leftPageMarkdown != null ? (
                    <ReactMarkdown>{leftPageMarkdown}</ReactMarkdown>
                  ) : (
                    <span className="text-slate-500">Loading markdown…</span>
                  )
                ) : (
                  <span className="whitespace-pre-wrap">{getPageText(left, selectedPage) || '(no text)'}</span>
                )}
              </div>
            </div>
            <div className="flex flex-col min-h-[320px] md:min-h-0">
              <div className="text-xs font-semibold text-slate-500 uppercase mb-2 shrink-0">
                {pagePreviewMarkdown && rightPageMarkdown != null ? `${rightLabel} markdown` : `${rightLabel} raw text`}
              </div>
              <div className="flex-1 min-h-0 overflow-auto text-sm text-slate-800 break-words p-2 bg-white rounded border border-slate-200 [&_table]:border [&_table]:border-slate-300 [&_th]:border [&_th]:border-slate-300 [&_td]:border [&_td]:border-slate-300 [&_th]:px-2 [&_td]:px-2">
                {pagePreviewMarkdown ? (
                  rightPageMarkdown != null ? (
                    <ReactMarkdown>{rightPageMarkdown}</ReactMarkdown>
                  ) : (
                    <span className="text-slate-500">Loading markdown…</span>
                  )
                ) : (
                  <span className="whitespace-pre-wrap">{getPageText(right, selectedPage) || '(no text)'}</span>
                )}
              </div>
            </div>
          </div>
          <div className="px-3 py-2 bg-slate-100 border-t border-slate-200">
            Page Extraction Accuracy: {selectedPageAccuracy != null ? `${selectedPageAccuracy.accuracyPct}%` : 'N/A'}
          </div>
        </div>
      ) : null}

      {!(viewMode === 'raw' && selectedPage != null) && (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4 border border-slate-200 rounded overflow-hidden min-h-0">
        <div
          ref={leftColRef}
          role="region"
          aria-label={`${leftLabel} structure`}
          className="p-3 sm:p-4 bg-slate-50 md:border-r border-slate-200 overflow-auto max-h-[320px] sm:max-h-[420px] min-h-0"
          onScroll={viewMode === 'tree' ? () => handleScroll('left') : undefined}
        >
          {viewMode === 'raw' ? (
            left ? <RawTextChips structure={left} label={`${leftLabel} (blocks as chips)`} /> : <p className="text-slate-500">No data</p>
          ) : (
            <>
              <div className="text-xs font-semibold text-slate-500 uppercase mb-2">{leftLabel} structure</div>
              {left ? <StructureTree structure={left} mismatches={mismatches} side="docx" scrollTargetId={FIRST_MISMATCH_HIGHLIGHT_ID} /> : <p className="text-slate-500">No data</p>}
            </>
          )}
        </div>
        <div
          ref={rightColRef}
          role="region"
          aria-label={`${rightLabel} structure`}
          className="p-3 sm:p-4 bg-slate-50 overflow-auto max-h-[320px] sm:max-h-[420px] min-h-0"
          onScroll={viewMode === 'tree' ? () => handleScroll('right') : undefined}
        >
          {viewMode === 'raw' ? (
            right ? <RawTextChips structure={right} label={`${rightLabel} (blocks as chips)`} /> : <p className="text-slate-500">No data</p>
          ) : (
            <>
              <div className="text-xs font-semibold text-slate-500 uppercase mb-2">{rightLabel} structure{rightLabel === 'Textract' ? ' (AWS Textract)' : ''}</div>
              {right ? <StructureTree structure={right} mismatches={mismatches} side="pdf" /> : <p className="text-slate-500">No data</p>}
            </>
          )}
        </div>
      </div>
      )}
      {left && right && diffSelection !== null && (
        <div className="mt-4 border border-slate-200 rounded p-3 sm:p-4 overflow-x-auto min-w-0">
          <h3 className="text-sm font-medium mb-2">Diff: Chapter {diffSelection.chapterIndex + 1}</h3>
          <ReactDiffViewer
            oldValue={left.chapters[diffSelection.chapterIndex]?.content_blocks.map((b) => b.content).join('\n') ?? ''}
            newValue={right.chapters[diffSelection.chapterIndex]?.content_blocks.map((b) => b.content).join('\n') ?? ''}
            splitView
            useDarkTheme={false}
          />
        </div>
      )}
      {left && right && left.chapters.length > 0 && (() => {
        const totalChapters = left.chapters.length;
        const totalChapterPages = Math.ceil(totalChapters / CHAPTERS_PER_PAGE) || 1;
        const currentChapterPage = Math.min(chapterPage, totalChapterPages - 1);
        const startIdx = currentChapterPage * CHAPTERS_PER_PAGE;
        const endIdx = Math.min(startIdx + CHAPTERS_PER_PAGE, totalChapters);
        const showFirstLast = totalChapters > CHAPTERS_PER_PAGE;
        return (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-sm text-slate-600 w-full sm:w-auto">Show diff for chapter:</span>
            <div className="flex flex-wrap items-center gap-1">
              <button
                type="button"
                onClick={() => setChapterPage((p) => Math.max(0, p - 1))}
                disabled={currentChapterPage === 0}
                className="px-2 py-1 rounded text-sm bg-slate-200 hover:bg-slate-300 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              {showFirstLast && startIdx > 0 && (
                <>
                  <button
                    type="button"
                    onClick={() => setDiffSelection((prev) => (prev?.chapterIndex === 0 ? null : { chapterIndex: 0 }))}
                    className={`px-2 py-1 rounded text-sm ${diffSelection?.chapterIndex === 0 ? 'bg-slate-700 text-white' : 'bg-slate-200 hover:bg-slate-300'}`}
                  >
                    1
                  </button>
                  {startIdx > 1 && <span className="px-1 text-slate-500">…</span>}
                </>
              )}
              {Array.from({ length: endIdx - startIdx }, (_, i) => startIdx + i).map((idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setDiffSelection((prev) => (prev?.chapterIndex === idx ? null : { chapterIndex: idx }))}
                  className={`px-2 py-1 rounded text-sm ${diffSelection?.chapterIndex === idx ? 'bg-slate-700 text-white' : 'bg-slate-200 hover:bg-slate-300'}`}
                >
                  {idx + 1}
                </button>
              ))}
              {showFirstLast && endIdx < totalChapters && (
                <>
                  {endIdx < totalChapters - 1 && <span className="px-1 text-slate-500">…</span>}
                  <button
                    type="button"
                    onClick={() => setDiffSelection((prev) => (prev?.chapterIndex === totalChapters - 1 ? null : { chapterIndex: totalChapters - 1 }))}
                    className={`px-2 py-1 rounded text-sm ${diffSelection?.chapterIndex === totalChapters - 1 ? 'bg-slate-700 text-white' : 'bg-slate-200 hover:bg-slate-300'}`}
                  >
                    {totalChapters}
                  </button>
                </>
              )}
              <button
                type="button"
                onClick={() => setChapterPage((p) => Math.min(totalChapterPages - 1, p + 1))}
                disabled={currentChapterPage >= totalChapterPages - 1}
                className="px-2 py-1 rounded text-sm bg-slate-200 hover:bg-slate-300 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
            <span className="text-xs text-slate-500">
              {currentChapterPage + 1} of {totalChapterPages} ({totalChapters} chapters)
            </span>
          </div>
        );
      })()}
    </section>
  );
}
