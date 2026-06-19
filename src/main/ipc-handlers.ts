import { ipcMain, dialog, shell, app, BrowserWindow } from 'electron'
import { execSync, spawn, ChildProcess } from 'child_process'
import { createWriteStream, existsSync, mkdirSync, unlinkSync } from 'fs'
import { join } from 'path'
import https from 'https'
import http from 'http'
import { BackendManager } from './backend-manager'
import { OllamaManager } from './ollama-manager'
import { checkDependencies, markSetupComplete } from './first-launch'

const isWindows = process.platform === 'win32'
const isMac = process.platform === 'darwin'

function getTempDir(): string {
  const dir = join(app.getPath('temp'), 'tcs-setup')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  return dir
}

function downloadFile(
  url: string,
  dest: string,
  onProgress?: (percent: number) => void
): Promise<string> {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http
    client.get(url, (response) => {
      if (response.statusCode === 301 || response.statusCode === 302) {
        downloadFile(response.headers.location!, dest, onProgress).then(resolve).catch(reject)
        return
      }
      const total = parseInt(response.headers['content-length'] || '0', 10)
      let downloaded = 0
      const file = createWriteStream(dest)
      response.on('data', (chunk: Buffer) => {
        downloaded += chunk.length
        if (total > 0 && onProgress) {
          onProgress(Math.round((downloaded / total) * 100))
        }
      })
      response.pipe(file)
      file.on('finish', () => { file.close(); resolve(dest) })
      file.on('error', reject)
    }).on('error', reject)
  })
}

export function setupIpcHandlers(
  backendManager: BackendManager,
  ollamaManager: OllamaManager
): void {
  ipcMain.handle('get-backend-url', () => {
    return `http://127.0.0.1:${backendManager.getPort()}`
  })

  ipcMain.handle('get-service-status', () => {
    return {
      backend: backendManager.isRunning(),
      ollama: ollamaManager.isRunning()
    }
  })

  ipcMain.handle('select-files', async (_, options: { filters?: Electron.FileFilter[]; multiSelections?: boolean }) => {
    const properties: ('openFile' | 'multiSelections')[] = ['openFile']
    if (options.multiSelections) {
      properties.push('multiSelections')
    }

    const result = await dialog.showOpenDialog({
      properties,
      filters: options.filters || [
        { name: 'Video Files', extensions: ['mp4', 'mov', 'avi', 'mkv'] },
        { name: 'All Files', extensions: ['*'] }
      ]
    })

    return result.canceled ? [] : result.filePaths
  })

  ipcMain.handle('select-directory', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory']
    })

    return result.canceled ? null : result.filePaths[0]
  })

  ipcMain.handle('open-in-explorer', async (_, path: string) => {
    shell.showItemInFolder(path)
  })

  ipcMain.handle('open-external', async (_, url: string) => {
    shell.openExternal(url)
  })

  ipcMain.handle('check-dependencies', async () => {
    return checkDependencies()
  })

  ipcMain.handle('run-setup-script', async (_, script: string) => {
    try {
      const output = execSync(script, {
        encoding: 'utf-8',
        timeout: 300_000,
        stdio: ['pipe', 'pipe', 'pipe']
      })
      return { success: true, output }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      return { success: false, output: message }
    }
  })

  ipcMain.handle('install-ollama', async (event) => {
    try {
      if (isMac) {
        if (existsSync('/opt/homebrew/bin/brew') || existsSync('/usr/local/bin/brew')) {
          execSync('brew install --cask ollama', { encoding: 'utf-8', timeout: 300_000 })
        } else {
          execSync('curl -fsSL https://ollama.com/install.sh | sh', {
            encoding: 'utf-8',
            timeout: 300_000,
            shell: '/bin/bash'
          })
        }
        return { success: true, message: 'Ollama installed via Homebrew' }
      } else {
        const dest = join(getTempDir(), 'OllamaSetup.exe')
        await downloadFile('https://ollama.com/download/OllamaSetup.exe', dest, (pct) => {
          event.sender.send('install-progress', { component: 'ollama', percent: pct })
        })
        execSync(`"${dest}" /VERYSILENT /NORESTART`, { timeout: 300_000 })
        try { unlinkSync(dest) } catch { /* cleanup best effort */ }
        return { success: true, message: 'Ollama installed silently' }
      }
    } catch (err: unknown) {
      return { success: false, message: err instanceof Error ? err.message : String(err) }
    }
  })

  ipcMain.handle('install-ffmpeg', async (event) => {
    try {
      if (isMac) {
        if (existsSync('/opt/homebrew/bin/brew') || existsSync('/usr/local/bin/brew')) {
          execSync('brew install ffmpeg', { encoding: 'utf-8', timeout: 600_000 })
        } else {
          return { success: false, message: 'Homebrew not found. Install Homebrew first: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"' }
        }
        return { success: true, message: 'FFmpeg installed via Homebrew' }
      } else {
        const zipDest = join(getTempDir(), 'ffmpeg.zip')
        const url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
        await downloadFile(url, zipDest, (pct) => {
          event.sender.send('install-progress', { component: 'ffmpeg', percent: pct })
        })
        const extractDir = join(getTempDir(), 'ffmpeg-extract')
        execSync(`powershell -Command "Expand-Archive -Path '${zipDest}' -DestinationPath '${extractDir}' -Force"`, { timeout: 120_000 })

        const binDir = join(app.getPath('userData'), 'bin')
        if (!existsSync(binDir)) mkdirSync(binDir, { recursive: true })

        const findExe = (name: string): string | null => {
          const search = (dir: string): string | null => {
            const { readdirSync, statSync } = require('fs')
            for (const entry of readdirSync(dir)) {
              const full = join(dir, entry)
              if (statSync(full).isDirectory()) {
                const found = search(full)
                if (found) return found
              } else if (entry === name) return full
            }
            return null
          }
          return search(extractDir)
        }

        const ffmpegPath = findExe('ffmpeg.exe')
        const ffprobePath = findExe('ffprobe.exe')
        if (ffmpegPath) require('fs').copyFileSync(ffmpegPath, join(binDir, 'ffmpeg.exe'))
        if (ffprobePath) require('fs').copyFileSync(ffprobePath, join(binDir, 'ffprobe.exe'))

        try { unlinkSync(zipDest) } catch { /* cleanup */ }
        return { success: true, message: `FFmpeg installed to ${binDir}` }
      }
    } catch (err: unknown) {
      return { success: false, message: err instanceof Error ? err.message : String(err) }
    }
  })

  ipcMain.handle('download-model', async (event, modelName: string) => {
    try {
      const ollamaCmd = isWindows ? 'ollama.exe' : 'ollama'
      const child = spawn(ollamaCmd, ['pull', modelName], { stdio: ['pipe', 'pipe', 'pipe'] })

      let lastPercent = 0
      child.stderr?.on('data', (data: Buffer) => {
        const line = data.toString()
        const match = line.match(/(\d+)%/)
        if (match) {
          const pct = parseInt(match[1])
          if (pct !== lastPercent) {
            lastPercent = pct
            event.sender.send('install-progress', { component: 'model', model: modelName, percent: pct })
          }
        }
      })

      return new Promise((resolve) => {
        child.on('close', (code) => {
          resolve({
            success: code === 0,
            message: code === 0 ? `${modelName} downloaded` : `Failed with exit code ${code}`
          })
        })
        child.on('error', (err) => {
          resolve({ success: false, message: err.message })
        })
      })
    } catch (err: unknown) {
      return { success: false, message: err instanceof Error ? err.message : String(err) }
    }
  })

  ipcMain.handle('mark-setup-complete', () => {
    markSetupComplete()
  })

  // --- App Update (dev/source installs: git pull + reload) ---
  // Production builds use electron-updater via src/main/updater.ts instead.

  ipcMain.handle('pull-updates', async () => {
    try {
      const appPath = app.isPackaged
        ? app.getAppPath()
        : join(__dirname, '..', '..')

      const output = execSync('git pull origin main', {
        cwd: appPath,
        encoding: 'utf-8',
        timeout: 30_000,
        stdio: ['pipe', 'pipe', 'pipe']
      })

      const alreadyUpToDate = output.includes('Already up to date')
      return {
        success: true,
        message: alreadyUpToDate ? 'Already up to date' : 'Updates pulled successfully',
        changes: output.trim()
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      return { success: false, message, changes: '' }
    }
  })

  ipcMain.handle('reload-app', () => {
    BrowserWindow.getAllWindows().forEach((w) => w.reload())
    return { success: true }
  })

  ipcMain.handle('stop-app', async () => {
    const steps: { step: string; status: 'ok' | 'skipped' | 'error'; detail?: string }[] = []

    try {
      const port = backendManager.getPort()
      const res = await fetch(`http://127.0.0.1:${port}/api/v1/system/shutdown`, { method: 'POST' })
      steps.push({ step: 'backend', status: res.ok ? 'ok' : 'error', detail: `HTTP ${res.status}` })
    } catch (err: unknown) {
      steps.push({ step: 'backend', status: 'error', detail: err instanceof Error ? err.message : String(err) })
    }

    await new Promise((r) => setTimeout(r, 2000))

    if (ollamaManager.isRunning()) {
      try {
        await ollamaManager.stop()
        steps.push({ step: 'ollama', status: 'ok' })
      } catch (err: unknown) {
        steps.push({ step: 'ollama', status: 'error', detail: err instanceof Error ? err.message : String(err) })
      }
    } else {
      steps.push({ step: 'ollama', status: 'skipped', detail: 'not running' })
    }

    await backendManager.stop()
    steps.push({ step: 'processes_cleaned', status: 'ok' })

    setTimeout(() => app.quit(), 300)
    return { success: true, steps }
  })
}
