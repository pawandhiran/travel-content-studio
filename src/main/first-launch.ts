import { app } from 'electron'
import { existsSync, mkdirSync, writeFileSync } from 'fs'
import { join } from 'path'
import { execSync } from 'child_process'
import { net } from 'electron'

interface DependencyStatus {
  ollama: { installed: boolean; running: boolean; path: string | null }
  ffmpeg: { installed: boolean; path: string | null }
  models: { downloaded: string[]; recommended: string[] }
  firstLaunch: boolean
}

const SETUP_DIR = join(app.getPath('home'), '.travel-content-studio')
const MARKER_FILE = join(SETUP_DIR, '.setup-complete')

function whichCommand(): string {
  return process.platform === 'win32' ? 'where' : 'which'
}

function safeEnv(): NodeJS.ProcessEnv {
  const e = { ...process.env }
  delete e.ELECTRON_RUN_AS_NODE
  return e
}

function findBinary(name: string): string | null {
  try {
    const result = execSync(`${whichCommand()} ${name}`, {
      encoding: 'utf-8',
      timeout: 5000,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: safeEnv()
    })
    return result.trim().split('\n')[0] || null
  } catch {
    return null
  }
}

function queryOllamaModels(): Promise<string[]> {
  return new Promise((resolve) => {
    const request = net.request('http://localhost:11434/api/tags')
    let body = ''

    request.on('response', (response) => {
      response.on('data', (chunk) => {
        body += chunk.toString()
      })
      response.on('end', () => {
        try {
          const data = JSON.parse(body)
          const names = (data.models || []).map(
            (m: { name?: string }) => m.name || ''
          )
          resolve(names.filter(Boolean))
        } catch {
          resolve([])
        }
      })
    })

    request.on('error', () => resolve([]))
    request.setTimeout(5000, () => {
      request.abort()
      resolve([])
    })
    request.end()
  })
}

function isOllamaRunning(): Promise<boolean> {
  return new Promise((resolve) => {
    const request = net.request('http://localhost:11434/api/version')

    request.on('response', (response) => {
      response.on('data', () => {})
      response.on('end', () => resolve(response.statusCode === 200))
    })

    request.on('error', () => resolve(false))
    request.setTimeout(3000, () => {
      request.abort()
      resolve(false)
    })
    request.end()
  })
}

export async function checkDependencies(): Promise<DependencyStatus> {
  const ollamaPath = findBinary('ollama')
  const ffmpegPath = findBinary('ffmpeg')
  const running = ollamaPath ? await isOllamaRunning() : false
  const models = running ? await queryOllamaModels() : []

  return {
    ollama: {
      installed: ollamaPath !== null,
      running,
      path: ollamaPath
    },
    ffmpeg: {
      installed: ffmpegPath !== null,
      path: ffmpegPath
    },
    models: {
      downloaded: models,
      recommended: ['llama3.2:3b', 'llama3.2:1b', 'gemma3:4b']
    },
    firstLaunch: !existsSync(MARKER_FILE)
  }
}

export function markSetupComplete(): void {
  if (!existsSync(SETUP_DIR)) {
    mkdirSync(SETUP_DIR, { recursive: true })
  }
  writeFileSync(MARKER_FILE, new Date().toISOString(), 'utf-8')
}

export function isFirstLaunch(): boolean {
  return !existsSync(MARKER_FILE)
}
