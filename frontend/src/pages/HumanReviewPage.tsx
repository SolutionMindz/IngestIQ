import { useState } from 'react';
import ReviewQueue from '../components/HumanReview/ReviewQueue';
import ReviewTask from '../components/HumanReview/ReviewTask';
import ReviewerDashboard from '../components/HumanReview/ReviewerDashboard';

// In a real app this comes from auth context; for now it's a fixed reviewer ID
const CURRENT_REVIEWER_ID = 'current-user';

export default function HumanReviewPage() {
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [completedTaskId, setCompletedTaskId] = useState<string | null>(null);

  function handleSelectTask(taskId: string) {
    setSelectedTaskId(taskId);
    setCompletedTaskId(null);
  }

  function handleTaskComplete() {
    setCompletedTaskId(selectedTaskId);
    setSelectedTaskId(null);
  }

  return (
    <div className="flex bg-white overflow-hidden rounded-lg border border-gray-200" style={{ height: 'calc(100vh - 80px)' }}>
      {/* Left sidebar — Review Queue */}
      <aside className="w-72 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col overflow-hidden">
        <ReviewQueue
          reviewerId={CURRENT_REVIEWER_ID}
          selectedTaskId={selectedTaskId}
          onSelectTask={handleSelectTask}
        />
      </aside>

      {/* Main panel */}
      <main className="flex-1 overflow-y-auto p-6">
        {completedTaskId && (
          <div className="mb-4 px-4 py-3 bg-green-50 border border-green-200 rounded-lg flex items-center gap-2">
            <span className="text-green-600 font-medium text-sm">Correction submitted successfully.</span>
            <button
              onClick={() => setCompletedTaskId(null)}
              className="ml-auto text-green-500 hover:text-green-700 text-xs"
            >
              Dismiss
            </button>
          </div>
        )}

        {selectedTaskId ? (
          <ReviewTask
            taskId={selectedTaskId}
            reviewerId={CURRENT_REVIEWER_ID}
            onComplete={handleTaskComplete}
          />
        ) : (
          <ReviewerDashboard reviewerId={CURRENT_REVIEWER_ID} />
        )}
      </main>
    </div>
  );
}
