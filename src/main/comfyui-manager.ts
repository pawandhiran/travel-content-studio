import { ChildProcess, spawn } from 'child_process'
import { join } from 'path'
import { app } from 'electron'

const COMFYUI_PORT = 8188
const HEALTH_CHECK_URL = `http://127.0.0.1:${COMFYUI_PORT}/system_stats`
const MAX_RETRIES = 30
const RETRY_INTERVAL_MS = 2000

const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'

export class ComfyUIManager {
  private process: ChildProcess | null = null
  private running = false

  async start(): Promise<void> {
    if (this.running) return

    if (await this.isAlreadyRunning()) {
      console.log('[ComfyUIManager] ComfyUI is already running')
      this.running = true
      return
    }

    const comfyPath = this.getComfyUIPath()
    console.log(`[ComfyUIManager] Starting ComfyUI from: ${comfyPath}`)

    this.process = spawn(pythonCmd, ['-m', 'comfyui', '--listen', '127.0.0.1', '--port', String(COMFYUI_PORT)], {
      cwd: comfyPath,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' }
    })

    this.process.stdout?.on('data', (data) => {
      console.log(`[ComfyUI] ${data.toString().trim()}`)
    })

    this.process.stderr?.on('data', (data) => {
      console.error(`[ComfyUI] ${data.toString().trim()}`)
    })

    this.process.on('exit', (code) => {
      console.log(`[ComfyUIManager] ComfyUI exited with code ${code}`)
      this.running = false
    })

    await this.waitForHealth()
    this.running = true
    console.log('[ComfyUIManager] ComfyUI is ready')
  }

  async stop(): Promise<void> {
    if (!this.process || !this.running) return

    console.log('[ComfyUIManager] Stopping ComfyUI...')
    this.process.kill('SIGTERM')
    this.running = false
  }

  isRunning(): boolean {
    return this.running
  }

  getPort(): number {
    return COMFYUI_PORT
  }

  private getComfyUIPath(): string {
    const resourcesPath = process.resourcesPath || join(app.getAppPath(), '..')
    return join(resourcesPath, 'comfyui')
  }

  private async isAlreadyRunning(): Promise<boolean> {
    try {
      const response = await fetch(HEALTH_CHECK_URL)
      return response.ok
    } catch {
      return false
    }
  }

  private async waitForHealth(): Promise<void> {
    for (let i = 0; i < MAX_RETRIES; i++) {
      try {
        const response = await fetch(HEALTH_CHECK_URL)
        if (response.ok) return
      } catch {
        // Not ready yet
      }
      await new Promise((resolve) => setTimeout(resolve, RETRY_INTERVAL_MS))
    }
    throw new Error('ComfyUI failed to start')
  }
}
