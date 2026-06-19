import { create } from 'zustand'
import { apiClient } from '../services/apiClient'

export interface Job {
  id: string
  project_id: string | null
  job_type: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number
  error: string | null
  started_at: string | null
  completed_at: string | null
}

interface JobState {
  jobs: Job[]
  fetchJobs: () => Promise<void>
  cancelJob: (id: string) => Promise<void>
  updateJobFromEvent: (job: Partial<Job> & { id: string }) => void
}

export const useJobStore = create<JobState>((set, get) => ({
  jobs: [],

  fetchJobs: async () => {
    try {
      const data = await apiClient.get('/jobs')
      set({ jobs: data.jobs || data })
    } catch {
      // Silently fail
    }
  },

  cancelJob: async (id: string) => {
    await apiClient.post(`/jobs/${id}/cancel`)
    set({
      jobs: get().jobs.map((j) => (j.id === id ? { ...j, status: 'cancelled' as const } : j))
    })
  },

  updateJobFromEvent: (job: Partial<Job> & { id: string }) => {
    set({
      jobs: get().jobs.map((j) => (j.id === job.id ? { ...j, ...job } : j))
    })
  }
}))
