import { useEffect, useState } from 'react';
import type { A2ITask, A2ITaskStatus } from '../../types/a2i';
import { fetchAllA2ITasks, assignA2ITask } from '../../api';

interface ReviewQueueProps {
  reviewerId: string;
  selectedTaskId: string | null;
  onSelectTask: (taskId: string) => void;
}

type StatusFilter = 'all' | 'pending' | 'mine' | 'completed';

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'mine', label: 'Assigned to Me' },
  { key: 'completed', label: 'Completed' },
];

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-700',
  assigned: 'bg-blue-100 text-blue-700',
  in_review: 'bg-indigo-100 text-indigo-700',
  under_review: 'bg-purple-100 text-purple-700',
  completed: 'bg-green-100 text-green-700',
  auto_verified: 'bg-gray-100 text-gray-600',
  failed: 'bg-red-100 text-red-700',
};

function statusLabel(status: A2ITaskStatus): string {
  return status.replace(/_/g, ' ');
}

export default function ReviewQueue({ reviewerId, selectedTaskId, onSelectTask }: ReviewQueueProps) {
  const [tasks, setTasks] = useState<A2ITask[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<StatusFilter>('all');
  const [assigning, setAssigning] = useState<string | null>(null);

  useEffect(() => {
    loadTasks();
  }, []);

  async function loadTasks() {
    setLoading(true);
    try {
      const all = await fetchAllA2ITasks({ limit: 100 });
      setTasks(all);
    } finally {
      setLoading(false);
    }
  }

  function filteredTasks(): A2ITask[] {
    switch (activeTab) {
      case 'pending':
        return tasks.filter((t) => t.status === 'pending');
      case 'mine':
        return tasks.filter((t) => t.assignedTo === reviewerId);
      case 'completed':
        return tasks.filter((t) => t.status === 'completed' || t.status === 'auto_verified');
      default:
        return tasks;
    }
  }

  async function handleSelectTask(task: A2ITask) {
    if (task.status === 'pending') {
      setAssigning(task.id);
      try {
        const updated = await assignA2ITask(task.id, reviewerId);
        setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
      } catch {
        // non-fatal: still open the task
      } finally {
        setAssigning(null);
      }
    }
    onSelectTask(task.id);
  }

  const visible = filteredTasks();

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold text-gray-700">Review Queue</h2>
          <button
            onClick={loadTasks}
            className="text-xs text-indigo-600 hover:text-indigo-800"
          >
            Refresh
          </button>
        </div>
        {/* Status filter tabs */}
        <div className="flex gap-1">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-gray-400 text-sm">
            Loading…
          </div>
        ) : visible.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-gray-400 text-sm">
            No tasks
          </div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {visible.map((task) => (
              <li
                key={task.id}
                onClick={() => handleSelectTask(task)}
                className={`px-4 py-3 cursor-pointer hover:bg-indigo-50 transition-colors ${
                  selectedTaskId === task.id ? 'bg-indigo-50 border-l-2 border-indigo-500' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-gray-800 truncate">
                      Doc {task.documentId.slice(0, 8)}…
                      <span className="ml-1 text-gray-500 font-normal">· Page {task.pageNumber}</span>
                    </p>
                    <p className="text-xs text-gray-500 truncate mt-0.5" title={task.triggerReason}>
                      {task.triggerReason}
                    </p>
                    {task.confidenceScore != null && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        Conf: {task.confidenceScore.toFixed(1)}%
                      </p>
                    )}
                    {task.assignedTo && (
                      <p className="text-xs text-blue-500 mt-0.5 truncate">
                        → {task.assignedTo === reviewerId ? 'You' : task.assignedTo}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[task.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {statusLabel(task.status)}
                    </span>
                    {assigning === task.id && (
                      <span className="text-xs text-indigo-500">Assigning…</span>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
