import { create } from 'zustand'
import { apiClient } from '../services/apiClient'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

interface HardwareInfo {
  ramGb: number
  gpuName: string
  vramGb: number
  gpuType: string | null // "nvidia", "apple_silicon", "integrated", or null
  cudaAvailable: boolean
  metalAvailable: boolean
}

interface SystemState {
  backendStatus: ConnectionStatus
  ollamaStatus: ConnectionStatus
  hardware: HardwareInfo | null
  activeModel: string | null
  availableModels: string[]
  checkHealth: () => Promise<void>
  fetchHardware: () => Promise<void>
  fetchModels: () => Promise<void>
  switchModel: (model: string) => Promise<void>
  pullModel: (modelId: string) => Promise<{ success: boolean; error?: string }>
}

export const useSystemStore = create<SystemState>((set) => ({
  backendStatus: 'connecting',
  ollamaStatus: 'connecting',
  hardware: null,
  activeModel: null,
  availableModels: [],

  checkHealth: async () => {
    try {
      const data = await apiClient.get<Record<string, unknown>>('/system/health')
      set({
        backendStatus: 'connected',
        ollamaStatus: data.ollama_status === 'connected' ? 'connected' : 'disconnected'
      })
    } catch {
      set({ backendStatus: 'disconnected', ollamaStatus: 'disconnected' })
    }
  },

  fetchHardware: async () => {
    try {
      const data = await apiClient.get<Record<string, unknown>>('/system/hardware')
      set({
        hardware: {
          ramGb: (data.ram_total_gb as number) || 0,
          gpuName: (data.gpu as string) || 'Unknown',
          vramGb: (data.gpu_vram_gb as number) || 0,
          gpuType: (data.gpu_type as string) || null,
          cudaAvailable: (data.cuda_available as boolean) || false,
          metalAvailable: (data.metal_available as boolean) || false
        }
      })
    } catch {
      // Hardware detection failed
    }
  },

  fetchModels: async () => {
    try {
      const data = await apiClient.get<{
        models: { model_id: string; name: string }[]
        active_model: string | null
        recommended_model: string
      }>('/system/models')
      const models = data.models || []
      set({
        availableModels: models.map((m) => m.name || m.model_id),
        activeModel: data.active_model || null
      })
    } catch {
      // Model fetch failed
    }
  },

  switchModel: async (model: string) => {
    await apiClient.post('/system/models/switch', { model_id: model })
    set({ activeModel: model })
  },

  pullModel: async (modelId: string) => {
    try {
      const data = await apiClient.post<{ status?: string; error?: string }>(
        '/system/models/pull',
        { model_id: modelId }
      )
      if (data.error) return { success: false, error: data.error }
      return { success: true }
    } catch (err) {
      return { success: false, error: (err as Error).message }
    }
  }
}))
