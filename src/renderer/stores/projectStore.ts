import { create } from 'zustand'
import { apiClient } from '../services/apiClient'

export interface Project {
  id: string
  name: string
  description: string
  template: string | null
  status: string
  folder_path: string
  created_at: string
  updated_at: string
  video_count?: number
  content_count?: number
}

interface ProjectState {
  projects: Project[]
  currentProject: Project | null
  loading: boolean
  error: string | null
  fetchProjects: (search?: string) => Promise<void>
  fetchProject: (id: string) => Promise<void>
  createProject: (name: string, description: string, template?: string) => Promise<Project>
  updateProject: (id: string, updates: Partial<Project>) => Promise<void>
  deleteProject: (id: string) => Promise<void>
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  currentProject: null,
  loading: false,
  error: null,

  fetchProjects: async (search?: string) => {
    set({ loading: true, error: null })
    try {
      const params = search ? `?search=${encodeURIComponent(search)}` : ''
      const data = await apiClient.get(`/projects${params}`)
      set({ projects: data.projects || data, loading: false })
    } catch (e) {
      set({ error: (e as Error).message, loading: false })
    }
  },

  fetchProject: async (id: string) => {
    set({ loading: true, error: null })
    try {
      const data = await apiClient.get(`/projects/${id}`)
      set({ currentProject: data, loading: false })
    } catch (e) {
      set({ error: (e as Error).message, loading: false })
    }
  },

  createProject: async (name: string, description: string, template?: string) => {
    const data = await apiClient.post('/projects', { name, description, template })
    set({ projects: [data, ...get().projects] })
    return data
  },

  updateProject: async (id: string, updates: Partial<Project>) => {
    const data = await apiClient.put(`/projects/${id}`, updates)
    set({
      currentProject: data,
      projects: get().projects.map((p) => (p.id === id ? data : p))
    })
  },

  deleteProject: async (id: string) => {
    await apiClient.delete(`/projects/${id}`)
    set({
      projects: get().projects.filter((p) => p.id !== id),
      currentProject: get().currentProject?.id === id ? null : get().currentProject
    })
  }
}))
