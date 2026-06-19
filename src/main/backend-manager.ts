import { ChildProcess, spawn } from 'child_process'
import { join } from 'path'
import { app } from 'electron'
import { is } from '@electron-toolkit/utils'

const BACKEND_PORT = 8420
const HEALTH_CHECK_URL = `http://127.0.0.1:${BACKEND_PORT}/api/v1/system/health`
const MAX_RETRIES = 30
const RETRY_INTERVAL_MS = 1000

const isWindows = process.platform === 'win32'
const pythonCmd = isWindows ? 'python' : 'python3'

function getBundledBinDir(): string {
  const resourcesPath = process.resourcesPath || join(app.getAppPath(), '..')
  return join(resourcesPath, 'bin')
}

function getSpawnEnv(): NodeJS.ProcessEnv {
  const binDir = getBundledBinDir()
  const sep = isWindows ? ';' : ':'
  return {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    PATH: `${binDir}${sep}${process.env.PATH || ''}`
  }
}

export class BackendManager {
  private process: ChildProcess | null = null
  private running = false

  async start(): Promise<void> {
    if (this.running) return

    const backendPath = this.getBackendPath()
    console.log(`[BackendManager] Starting backend from: ${backendPath}`)

    if (is.dev) {
      const backendDir = join(app.getAppPath(), 'backend')
      const venvPython = isWindows
        ? join(backendDir, '.venv', 'Scripts', 'python.exe')
        : join(backendDir, '.venv', 'bin', 'python3')
      const usePython = require('fs').existsSync(venvPython) ? venvPython : pythonCmd
      console.log(`[BackendManager] Using Python: ${usePython}`)

      this.process = spawn(usePython, ['main.py'], {
        cwd: backendDir,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: getSpawnEnv()
      })
    } else {
      this.process = spawn(backendPath, [], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: getSpawnEnv()
      })
    }

    this.process.stdout?.on('data', (data) => {
      console.log(`[Backend] ${data.toString().trim()}`)
    })

    this.process.stderr?.on('data', (data) => {
      console.error(`[Backend] ${data.toString().trim()}`)
    })

    this.process.on('exit', (code) => {
      console.log(`[BackendManager] Backend exited with code ${code}`)
      this.running = false
    })

    await this.waitForHealth()
    this.running = true
    console.log('[BackendManager] Backend is ready')
  }

  async stop(): Promise<void> {
    if (!this.process || !this.running) return

    console.log('[BackendManager] Stopping backend...')
    try {
      await fetch(`http://127.0.0.1:${BACKEND_PORT}/api/v1/system/shutdown`, {
        method: 'POST'
      }).catch(() => {})
    } catch {
      // Ignore fetch errors during shutdown
    }

    setTimeout(() => {
      if (this.process && !this.process.killed) {
        this.process.kill('SIGTERM')
      }
    }, 2000)

    this.running = false
  }

  isRunning(): boolean {
    return this.running
  }

  getPort(): number {
    return BACKEND_PORT
  }

  private getBackendPath(): string {
    if (is.dev) {
      return join(app.getAppPath(), 'backend', 'main.py')
    }
    const resourcesPath = process.resourcesPath || join(app.getAppPath(), '..')
    const ext = isWindows ? '.exe' : ''
    return join(resourcesPath, 'backend', `travel-content-studio-backend${ext}`)
  }

  private async waitForHealth(): Promise<void> {
    for (let i = 0; i < MAX_RETRIES; i++) {
      try {
        const response = await fetch(HEALTH_CHECK_URL)
        if (response.ok) return
      } catch {
        // Server not ready yet
      }
      await new Promise((resolve) => setTimeout(resolve, RETRY_INTERVAL_MS))
    }
    throw new Error(`Backend failed to start after ${MAX_RETRIES} retries`)
  }
}
