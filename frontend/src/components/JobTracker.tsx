import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

interface Job {
  id: string;
  agent: string;
  ticker: string;
  status: 'pending' | 'running' | 'complete' | 'failed' | 'cancelled';
  progress: string;
  error: string;
  created_at: number;
  started_at: number;
  completed_at: number;
  duration_s: number;
}

const AGENT_LABELS: Record<string, string> = {
  screener: 'Screener',
  thesis: 'Thesis',
  ic_review: 'IC Review',
  pipeline: 'Pipeline',
  memo: 'Memo',
  research_report: 'Research Report',
  investment_memo: 'Investment Memo',
  portfolio: 'Portfolio',
  allocator: 'Allocator',
};

function elapsed(startedAt: number): string {
  const s = Math.floor(Date.now() / 1000 - startedAt);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function JobTracker() {
  const queryClient = useQueryClient();
  // Tick every second so elapsed() re-renders live while jobs are running
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const { data } = useQuery({
    queryKey: ['jobs'],
    queryFn: api.listJobs,
    refetchInterval: 2000, // Poll every 2s
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  });

  const jobs: Job[] = data?.jobs || [];

  // When a memo job completes, refresh the approved list so Generate → Read flips
  const prevJobsRef = React.useRef<Record<string, string>>({});
  useEffect(() => {
    const prev = prevJobsRef.current;
    const next: Record<string, string> = {};
    for (const job of jobs) {
      next[job.id] = job.status;
      if ((job.agent === 'memo' || job.agent === 'research_report' || job.agent === 'investment_memo') && job.status === 'complete' && prev[job.id] === 'running') {
        queryClient.invalidateQueries({ queryKey: ['approved'] });
      }
    }
    prevJobsRef.current = next;
  }, [jobs, queryClient]);

  const active = jobs.filter(j => j.status === 'running');
  const actuallyRunning = active.filter(j => j.progress !== 'queued');
  const queued = active.filter(j => j.progress === 'queued');
  const recentDone = jobs
    .filter(j => j.status === 'complete' || j.status === 'failed' || j.status === 'cancelled')
    .filter(j => j.completed_at > Date.now() / 1000 - 60) // Last 60s
    .slice(0, 3);

  if (active.length === 0 && recentDone.length === 0) return null;

  return (
    <div style={{
      background: active.length > 0 ? 'rgba(245, 166, 35, 0.08)' : 'var(--bg-secondary)',
      borderBottom: active.length > 0 ? '2px solid var(--accent)' : '1px solid var(--border)',
      padding: '8px 16px',
      fontSize: 'var(--text-sm)',
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      minHeight: 36,
    }}>
      {actuallyRunning.map(job => (
        <div key={job.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)',
            animation: 'pulse 1.5s infinite', display: 'inline-block',
          }} />
          <span style={{ color: 'var(--accent)', fontWeight: 600 }}>
            {AGENT_LABELS[job.agent] || job.agent}
            {job.ticker ? ` (${job.ticker})` : ''}
          </span>
          <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
            {job.progress || 'running'}
          </span>
          <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
            {elapsed(job.started_at)}
          </span>
          <button
            onClick={() => cancelMutation.mutate(job.id)}
            disabled={cancelMutation.isPending}
            style={{
              background: 'none',
              border: '1px solid var(--border)',
              borderRadius: 4,
              color: 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: 11,
              padding: '1px 7px',
              lineHeight: '16px',
              opacity: cancelMutation.isPending ? 0.5 : 1,
            }}
            title="Stop job"
          >
            stop
          </button>
        </div>
      ))}
      {queued.map(job => (
        <div key={job.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', background: 'var(--text-muted)',
            display: 'inline-block',
          }} />
          <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>
            {AGENT_LABELS[job.agent] || job.agent}
            {job.ticker ? ` (${job.ticker})` : ''}
          </span>
          <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
            queued
          </span>
          <button
            onClick={() => cancelMutation.mutate(job.id)}
            disabled={cancelMutation.isPending}
            style={{
              background: 'none',
              border: '1px solid var(--border)',
              borderRadius: 4,
              color: 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: 11,
              padding: '1px 7px',
              lineHeight: '16px',
              opacity: cancelMutation.isPending ? 0.5 : 1,
            }}
            title="Cancel queued job"
          >
            cancel
          </button>
        </div>
      ))}
      {recentDone.map(job => (
        <div key={job.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: job.status === 'complete' ? 'var(--positive)' : job.status === 'cancelled' ? 'var(--text-muted)' : 'var(--negative)',
            display: 'inline-block',
          }} />
          <span style={{ color: job.status === 'complete' ? 'var(--positive)' : job.status === 'cancelled' ? 'var(--text-muted)' : 'var(--negative)' }}>
            {AGENT_LABELS[job.agent] || job.agent}
            {job.ticker ? ` (${job.ticker})` : ''}
          </span>
          <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
            {job.status === 'complete' ? `done ${job.duration_s.toFixed(0)}s` : job.status === 'cancelled' ? 'stopped' : job.error || 'failed'}
          </span>
        </div>
      ))}
      {active.length > 0 && (
        <span style={{ marginLeft: 'auto', color: 'var(--text-muted)' }}>
          {actuallyRunning.length > 0 ? `${actuallyRunning.length} running` : ''}
          {actuallyRunning.length > 0 && queued.length > 0 ? ' · ' : ''}
          {queued.length > 0 ? `${queued.length} queued` : ''}
        </span>
      )}
    </div>
  );
}

/** Hook to get running job count for sidebar */
export function useRunningJobs() {
  const { data } = useQuery({
    queryKey: ['jobs'],
    queryFn: api.listJobs,
    refetchInterval: 2000,
  });
  const jobs: Job[] = data?.jobs || [];
  return jobs.filter(j => j.status === 'running');
}
