import { useEffect, useState } from 'react';
import type { ReviewerStats } from '../../types/a2i';
import { fetchReviewerStats } from '../../api';

interface ReviewerDashboardProps {
  reviewerId: string;
}

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}

function StatCard({ label, value, sub, color = 'text-indigo-600' }: StatCardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

export default function ReviewerDashboard({ reviewerId }: ReviewerDashboardProps) {
  const [stats, setStats] = useState<ReviewerStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchReviewerStats(reviewerId)
      .then(setStats)
      .catch(() => setError('Could not load reviewer stats.'))
      .finally(() => setLoading(false));
  }, [reviewerId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto mb-3" />
          Loading stats…
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
        {error ?? 'No data available.'}
      </div>
    );
  }

  const completionRate = stats.totalAssigned > 0
    ? Math.round((stats.completed / stats.totalAssigned) * 100)
    : 0;

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-800">Reviewer Dashboard</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Stats for <span className="font-medium text-gray-700">{reviewerId}</span>
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatCard
          label="Total Assigned"
          value={stats.totalAssigned}
          sub="tasks assigned to you"
        />
        <StatCard
          label="Completed"
          value={stats.completed}
          sub={`${completionRate}% completion rate`}
          color="text-green-600"
        />
        <StatCard
          label="Pending"
          value={stats.pending}
          sub="awaiting review"
          color={stats.pending > 0 ? 'text-amber-600' : 'text-gray-400'}
        />
        <StatCard
          label="Corrections Applied"
          value={stats.correctionsApplied}
          sub="pages with manual edits"
          color="text-red-500"
        />
        <StatCard
          label="Acceptance Rate"
          value={`${stats.acceptanceRate.toFixed(1)}%`}
          sub="tasks accepted without correction"
          color={stats.acceptanceRate >= 50 ? 'text-green-600' : 'text-amber-600'}
        />
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Status</p>
          <div className="mt-3 space-y-2">
            {stats.completed > 0 && (
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-green-500" />
                <span className="text-sm text-gray-700">{stats.completed} completed</span>
              </div>
            )}
            {stats.pending > 0 && (
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-amber-500" />
                <span className="text-sm text-gray-700">{stats.pending} pending</span>
              </div>
            )}
            {stats.correctionsApplied > 0 && (
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-red-400" />
                <span className="text-sm text-gray-700">{stats.correctionsApplied} corrected</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {stats.totalAssigned === 0 && (
        <div className="mt-8 text-center text-gray-400 text-sm">
          No tasks have been assigned to you yet.
        </div>
      )}
    </div>
  );
}
