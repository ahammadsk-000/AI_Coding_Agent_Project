/**
 * Live ingest progress per job.
 *
 * Stores the latest snapshot per (repoId, jobId). Updated by the SSE reader on
 * the repository page. Persisting to localStorage is intentional opt-out: live
 * progress is ephemeral and doesn't need to survive reloads.
 */
import { create } from "zustand";

import type { IngestJob } from "@/lib/api";

interface JobProgress {
  status: IngestJob["status"];
  filesSeen?: number;
  filesIndexed?: number;
  chunksIndexed?: number;
  bytesIndexed?: number;
  message?: string;
  finished?: boolean;
}

interface ReposState {
  progressByJobId: Record<string, JobProgress>;
  updateProgress: (jobId: string, patch: Partial<JobProgress>) => void;
  reset: (jobId: string) => void;
}

export const useReposStore = create<ReposState>((set) => ({
  progressByJobId: {},
  updateProgress: (jobId, patch) =>
    set((s) => ({
      progressByJobId: {
        ...s.progressByJobId,
        [jobId]: { ...(s.progressByJobId[jobId] ?? { status: "queued" }), ...patch },
      },
    })),
  reset: (jobId) =>
    set((s) => {
      const next = { ...s.progressByJobId };
      delete next[jobId];
      return { progressByJobId: next };
    }),
}));
