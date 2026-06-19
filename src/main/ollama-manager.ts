import { ChildProcess, spawn } from 'child_process'

const OLLAMA_PORT = 11434
const HEALTH_CHECK_URL = `http://127.0.0.1:${OLLAMA_PORT}/api/tags`
const MAX_RETRIES = 20
const RETRY_INTERVAL_MS = 2000

export class OllamaManager {
  private process: ChildProcess | null = null
  private running = false
  private externallyManaged = false

  async start(): Promise<void> {
    if (this.running) return

    if (await this.isOllamaAlreadyRunning()) {
      console.log('[OllamaManager] Ollama is already running externally')
      this.running = true
      this.externallyManaged = true
      return
    }

    console.log('[OllamaManager] Starting Ollama...')
    this.process = spawn('ollama', ['serve'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, OLLAMA_HOST: `127.0.0.1:${OLLAMA_PORT}` }
    })

    this.process.stdout?.on('data', (data) => {
      console.log(`[Ollama] ${data.toString().trim()}`)
    })

    this.process.stderr?.on('data', (data) => {
      console.error(`[Ollama] ${data.toString().trim()}`)
    })

    this.process.on('exit', (code) => {
      console.log(`[OllamaManager] Ollama exited with code ${code}`)
      this.running = false
    })

    await this.waitForHealth()
    this.running = true
    console.log('[OllamaManager] Ollama is ready')
  }

  async stop(): Promise<void> {
    if (this.externallyManaged) {
      console.log('[OllamaManager] Ollama is externally managed, not stopping')
      return
    }

    if (!this.process || !this.running) return

    console.log('[OllamaManager] Stopping Ollama...')
    this.process.kill('SIGTERM')
    this.running = false
  }

  isRunning(): boolean {
    return this.running
  }

  private async isOllamaAlreadyRunning(): Promise<boolean> {
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
    console.warn('[OllamaManager] Ollama failed to start - continuing without it')
  }
}
