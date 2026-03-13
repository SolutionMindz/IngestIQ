import { useState } from 'react';
import type { DiffItem, DiffAction } from '../../types/a2i';

interface DiffViewerProps {
  diffItems: DiffItem[];
  onAction: (id: string, action: DiffAction, correctedValue?: string) => void;
}

const DIFF_TYPE_LABEL: Record<string, string> = {
  changed_word: 'Changed',
  missing_word: 'Missing',
  extra_word: 'Extra',
  table_mismatch: 'Table',
};

const DIFF_TYPE_COLOR: Record<string, string> = {
  changed_word: 'bg-yellow-100 text-yellow-800',
  missing_word: 'bg-red-100 text-red-800',
  extra_word: 'bg-purple-100 text-purple-800',
  table_mismatch: 'bg-orange-100 text-orange-800',
};

interface EditingState {
  id: string;
  value: string;
}

export default function DiffViewer({ diffItems, onAction }: DiffViewerProps) {
  const [editing, setEditing] = useState<EditingState | null>(null);

  if (diffItems.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 text-sm">
        No differences detected.
      </div>
    );
  }

  const resolved = diffItems.filter((d) => d.action != null).length;

  function startEdit(item: DiffItem) {
    setEditing({ id: item.id, value: item.textractValue || item.nativeValue });
  }

  function submitEdit(id: string) {
    if (!editing || editing.id !== id) return;
    onAction(id, 'edited', editing.value);
    setEditing(null);
  }

  function cancelEdit() {
    setEditing(null);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">
          Word Differences
          <span className="ml-2 text-xs text-gray-500">({diffItems.length} items)</span>
        </h3>
        {resolved > 0 && (
          <span className="text-xs text-green-600 font-medium">
            {resolved} / {diffItems.length} resolved
          </span>
        )}
      </div>

      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 w-20">Type</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">PaddleOCR</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Textract</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 w-56">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {diffItems.map((item) => {
              const isResolved = item.action != null;
              const isEditing = editing?.id === item.id;

              let rowBg = '';
              if (item.action === 'accepted_native') rowBg = 'bg-green-50';
              else if (item.action === 'accepted_textract') rowBg = 'bg-blue-50';
              else if (item.action === 'edited') rowBg = 'bg-indigo-50';
              else if (item.action === 'rejected') rowBg = 'bg-gray-50 opacity-60';

              return (
                <tr key={item.id} className={rowBg}>
                  <td className="px-3 py-2">
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${DIFF_TYPE_COLOR[item.diffType] ?? 'bg-gray-100 text-gray-700'}`}>
                      {DIFF_TYPE_LABEL[item.diffType] ?? item.diffType}
                    </span>
                  </td>

                  <td className="px-3 py-2 font-mono text-xs">
                    {item.nativeValue ? (
                      <span className={item.action === 'accepted_native' ? 'text-green-700 font-semibold' : 'text-gray-800'}>
                        {item.nativeValue}
                      </span>
                    ) : (
                      <span className="text-gray-400 italic">—</span>
                    )}
                  </td>

                  <td className="px-3 py-2 font-mono text-xs">
                    {isEditing ? (
                      <input
                        type="text"
                        className="border border-indigo-400 rounded px-2 py-0.5 text-xs w-full focus:outline-none focus:ring-1 focus:ring-indigo-500"
                        value={editing.value}
                        onChange={(e) => setEditing({ id: item.id, value: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') submitEdit(item.id);
                          if (e.key === 'Escape') cancelEdit();
                        }}
                        autoFocus
                      />
                    ) : item.action === 'edited' && item.correctedValue != null ? (
                      <span className="text-indigo-700 font-semibold">{item.correctedValue}</span>
                    ) : item.textractValue ? (
                      <span className={item.action === 'accepted_textract' ? 'text-blue-700 font-semibold' : 'text-red-600'}>
                        {item.textractValue}
                      </span>
                    ) : (
                      <span className="text-gray-400 italic">—</span>
                    )}
                  </td>

                  <td className="px-3 py-2">
                    {isResolved && !isEditing ? (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-green-600 font-medium">
                          {item.action === 'accepted_textract' && '✓ Textract'}
                          {item.action === 'accepted_native' && '✓ PaddleOCR'}
                          {item.action === 'edited' && '✓ Edited'}
                          {item.action === 'rejected' && '✗ Rejected'}
                        </span>
                        <button
                          onClick={() => onAction(item.id, null)}
                          className="text-xs text-gray-400 hover:text-gray-600 underline"
                        >
                          undo
                        </button>
                      </div>
                    ) : isEditing ? (
                      <div className="flex gap-1">
                        <button
                          onClick={() => submitEdit(item.id)}
                          className="px-2 py-0.5 bg-indigo-600 text-white text-xs rounded hover:bg-indigo-700"
                        >
                          Save
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="px-2 py-0.5 bg-gray-200 text-gray-700 text-xs rounded hover:bg-gray-300"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="flex gap-1 flex-wrap">
                        <button
                          onClick={() => onAction(item.id, 'accepted_textract')}
                          className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded hover:bg-blue-200"
                          title="Use Textract value"
                        >
                          Textract
                        </button>
                        <button
                          onClick={() => onAction(item.id, 'accepted_native')}
                          className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded hover:bg-green-200"
                          title="Use PaddleOCR value"
                        >
                          PaddleOCR
                        </button>
                        <button
                          onClick={() => startEdit(item)}
                          className="px-2 py-0.5 bg-indigo-100 text-indigo-700 text-xs rounded hover:bg-indigo-200"
                          title="Edit value manually"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => onAction(item.id, 'rejected')}
                          className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded hover:bg-gray-200"
                          title="Skip this difference"
                        >
                          Skip
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
