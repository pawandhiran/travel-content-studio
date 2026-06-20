interface ElectronAPI {
  getBackendUrl(): Promise<string>
  getServiceStatus(): Promise<{ backend: boolean; ollama: boolean }>
  selectFiles(options?: { filters?: { name: string; extensions: string[] }[]; multiSelections?: boolean }): Promise<string[]>
  selectDirectory(): Promise<string | null>
  openInExplorer(path: string): Promise<void>
  openExternal(url: string): Promise<void>
  checkDependencies(): Promise<any>
  installOllama(): Promise<{ success: boolean; message: string }>
  installFfmpeg(): Promise<{ success: boolean; message: string }>
  downloadModel(model: string): Promise<{ success: boolean; message: string }>
  markSetupComplete(): Promise<void>
  pullUpdates(): Promise<{ success: boolean; message: string; changes: string }>
  reloadApp(): Promise<{ success: boolean }>
  stopApp(): Promise<{ success: boolean; steps: { step: string; status: string; detail?: string }[] }>
  onInstallProgress(callback: (data: { component: string; percent: number; model?: string }) => void): void
  onUpdateAvailable(callback: (info: { version: string }) => void): void
  onUpdateDownloaded(callback: () => void): void
  onAppClosing(callback: () => void): void
}

declare global {
  interface Window {
    api: ElectronAPI
  }
}

export {}
