import React, { useState, useEffect } from 'react';
import type { DocumentStructure, ContentBlock, Chapter } from '../../types/structure';
import type { ComparisonResult } from '../../types/comparison';
import type { PageAccuracyItem } from '../../api';
import { fetchStructure, fetchComparison, fetchPageAccuracy, screenshotUrl } from '../../api';

// --- Shared TypeBadge helpers (mirrors ChapterExplorer) ---
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

function OcrTable({ content }: { content: string }) {
  const lines = (content ?? '').split('\n').filter((l) => l.trim());
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
                <th key={i} className="text-left px-3 py-2 text-slate-600 font-medium border-b border-slate-200">{cell}</th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {dataRows.map((row, ri) => (
            <tr key={ri} className="border-b border-slate-100 last:border-0">
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-2 text-slate-700 align-top">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
  return <p className="mt-1 text-slate-800 leading-relaxed">{block.content}</p>;
}

function PageContent({ chapter }: { chapter: Chapter | null }) {
  if (!chapter) {
    return <p className="text-slate-400 italic text-sm">No extraction for this page.</p>;
  }
  if (chapter.content_blocks.length === 0) {
    return <p className="text-slate-400 italic text-sm">No content extracted — re-run extraction if this is unexpected.</p>;
  }
  return (
    <div>
      <div className="text-[10px] font-semibold tracking-widest text-slate-400 uppercase mb-3">
        Extracted Content
      </div>
      <div className="space-y-0">
        {chapter.content_blocks.map((block: ContentBlock) => (
          <div key={block.id} className="pb-3 mb-1 border-b border-slate-100 last:border-0">
            <TypeBadge type={block.type} />
            {renderBlockContent(block)}
          </div>
        ))}
      </div>
    </div>
  );
}

function StatBadge({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className="flex items-center gap-1.5 text-sm text-slate-700">
      {label}:{' '}
      <span
        className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-white text-xs font-bold ${
          ok ? 'bg-green-500' : 'bg-red-400'
        }`}
      >
        {ok ? '✓' : '✗'}
      </span>
    </span>
  );
}

function getChapterForPage(structure: DocumentStructure | null, page: number): Chapter | null {
  return structure?.chapters.find((c) => c.heading === `Page ${page}`) ?? null;
}

interface StructuralComparisonProps {
  documentId: string | null;
}

export default function StructuralComparison({ documentId }: StructuralComparisonProps) {
  const [pdf, setPdf] = useState<DocumentStructure | null>(null);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [pageAccuracyList, setPageAccuracyList] = useState<PageAccuracyItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedPage, setSelectedPage] = useState<number>(1);

  useEffect(() => {
    if (!documentId) {
      setPdf(null);
      setComparison(null);
      setPageAccuracyList([]);
      setSelectedPage(1);
      return;
    }
    setLoading(true);
    Promise.all([
      fetchStructure(documentId, 'pdf'),
      fetchComparison(documentId),
      fetchPageAccuracy(documentId).catch(() => []),
    ]).then(([p, c, acc]) => {
      setPdf(p ?? null);
      setComparison(c ?? null);
      setPageAccuracyList(Array.isArray(acc) ? acc : []);
      setLoading(false);
    });
  }, [documentId]);

  if (!documentId) {
    return (
      <section className="bg-white rounded-lg shadow p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">2. Structural Comparison Viewer</h2>
        <p className="text-slate-500">Select a document to view extracted structure.</p>
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

  const pageCount = pdf?.pageCount ?? pdf?.chapters?.length ?? 0;
  const chapter = getChapterForPage(pdf, selectedPage);
  const selectedAccuracy = pageAccuracyList.find((a) => a.pageNumber === selectedPage);

  return (
    <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
      <h2 className="text-lg font-semibold text-slate-800 mb-4">2. Structural Comparison Viewer</h2>

      {/* Stats bar */}
      {comparison && (
        <div className="mb-4 p-3 bg-slate-50 border border-slate-200 rounded-lg flex flex-wrap gap-4 items-center">
          <StatBadge label="Chapters" ok={comparison.chapterCountMatch} />
          <StatBadge label="Headings" ok={comparison.headingMatch} />
          <StatBadge label="Word count" ok={comparison.wordCountMatch} />
          {comparison.docxWordCount != null && (
            <span className="text-xs text-slate-500 ml-auto">
              {comparison.docxWordCount} words (PDF) vs {comparison.pdfWordCount} words (OCR)
            </span>
          )}
        </div>
      )}

      {/* Page selector */}
      {pageCount > 0 && (
        <div className="mb-4 flex items-center gap-3">
          <label htmlFor="sc-select-page" className="text-sm font-medium text-slate-700 whitespace-nowrap">
            Select page:
          </label>
          <select
            id="sc-select-page"
            value={selectedPage}
            onChange={(e) => setSelectedPage(Number(e.target.value))}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm bg-white min-w-[4rem]"
          >
            {Array.from({ length: pageCount }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          {selectedAccuracy != null && (
            <span className="text-xs text-slate-500">
              Page accuracy:{' '}
              <span className={
                selectedAccuracy.status === 'OK' ? 'text-green-600 font-medium' :
                selectedAccuracy.status === 'WARNING' ? 'text-amber-600 font-medium' :
                selectedAccuracy.status === 'FORMULA' ? 'text-blue-600 font-medium' :
                selectedAccuracy.status === 'IMAGE' ? 'text-purple-600 font-medium' :
                selectedAccuracy.status === 'SPARSE' ? 'text-gray-500 font-medium' :
                'text-red-600 font-medium'
              }>
                {selectedAccuracy.accuracyPct.toFixed(1)}%
              </span>
              {selectedAccuracy.status === 'FORMULA' && <span className="ml-1 italic">(formula page)</span>}
              {selectedAccuracy.status === 'IMAGE' && <span className="ml-1 italic">(image page)</span>}
              {selectedAccuracy.status === 'SPARSE' && <span className="ml-1 italic">(sparse page)</span>}
            </span>
          )}
        </div>
      )}

      {/* Main 2-column view: screenshot + extracted content */}
      {pageCount > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-0 border border-slate-200 rounded-lg overflow-hidden">
          {/* Left: PDF screenshot */}
          <div className="flex flex-col border-r border-slate-200">
            <div className="px-4 py-2.5 border-b border-slate-200 bg-slate-50">
              <span className="text-[10px] font-semibold tracking-widest text-slate-400 uppercase">Screenshot</span>
            </div>
            <div className="flex-1 overflow-auto max-h-[600px] flex justify-center bg-white p-2">
              {documentId && (
                <img
                  src={screenshotUrl(documentId, selectedPage)}
                  alt={`Page ${selectedPage}`}
                  className="max-w-full object-contain"
                />
              )}
            </div>
          </div>

          {/* Right: extracted content with TypeBadge pills */}
          <div className="flex flex-col">
            <div className="px-4 py-2.5 border-b border-slate-200 bg-slate-50">
              <span className="text-[10px] font-semibold tracking-widest text-slate-400 uppercase">Extracted Content</span>
            </div>
            <div className="flex-1 overflow-auto max-h-[600px] p-4 bg-white">
              <PageContent chapter={chapter} />
            </div>
          </div>
        </div>
      ) : (
        <p className="text-slate-500">No extraction data yet. Upload a PDF and wait for processing.</p>
      )}
    </section>
  );
}
