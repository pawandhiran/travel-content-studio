import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

const api = {
  getBackendUrl: (): Promise<string> => ipcRenderer.invoke('get-backend-url'),
  getServiceStatus: (): Promise<{ backend: boolean; ollama: boolean }> =>
    ipcRenderer.invoke('get-service-status'),
  selectFiles: (options?: {
    filters?: { name: string; extensions: string[] }[]
    multiSelections?: boolean
  }): Promise<string[]> => ipcRenderer.invoke('select-files', options || {}),
  selectDirectory: (): Promise<string | null> => ipcRenderer.invoke('select-directory'),
  openInExplorer: (path: string): Promise<void> => ipcRenderer.invoke('open-in-explorer', path),
  openExternal: (url: string): Promise<void> => ipcRenderer.invoke('open-external', url),
  checkDependencies: () => ipcRenderer.invoke('check-dependencies'),
  runSetupScript: (script: string): Promise<{ success: boolean; output: string }> =>
    ipcRenderer.invoke('run-setup-script', script),
  installOllama: (): Promise<{ success: boolean; message: string }> =>
    ipcRenderer.invoke('install-ollama'),
  installFfmpeg: (): Promise<{ success: boolean; message: string }> =>
    ipcRenderer.invoke('install-ffmpeg'),
  downloadModel: (model: string): Promise<{ success: boolean; message: string }> =>
    ipcRenderer.invoke('download-model', model),
  markSetupComplete: (): Promise<void> => ipcRenderer.invoke('mark-setup-complete'),
  pullUpdates: (): Promise<{ success: boolean; message: string; changes: string }> =>
    ipcRenderer.invoke('pull-updates'),
  reloadApp: (): Promise<{ success: boolean }> => ipcRenderer.invoke('reload-app'),
  stopApp: (): Promise<{ success: boolean; steps: { step: string; status: string; detail?: string }[] }> =>
    ipcRenderer.invoke('stop-app'),
  onInstallProgress: (callback: (data: { component: string; percent: number; model?: string }) => void) => {
    ipcRenderer.on('install-progress', (_, data) => callback(data))
  },
  onUpdateAvailable: (callback: (info: { version: string }) => void) => {
    ipcRenderer.on('update-available', (_, info) => callback(info))
  },
  onUpdateDownloaded: (callback: () => void) => {
    ipcRenderer.on('update-downloaded', () => callback())
  },
  onAppClosing: (callback: () => void) => {
    ipcRenderer.on('app-closing', () => callback())
  }
}

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('api', api)
  } catch {
    // Context isolation failed
  }
} else {
  // @ts-expect-error global augmentation
  window.electron = electronAPI
  // @ts-expect-error global augmentation
  window.api = api
}
