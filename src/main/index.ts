import { app, BrowserWindow, dialog, shell } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { setupIpcHandlers } from './ipc-handlers'
import { BackendManager } from './backend-manager'
import { OllamaManager } from './ollama-manager'
import { isFirstLaunch } from './first-launch'

let mainWindow: BrowserWindow | null = null
let isQuitting = false
const backendManager = new BackendManager()
const ollamaManager = new OllamaManager()

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    title: 'Travel Content Studio',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show()
  })

  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault()
      mainWindow?.webContents.send('app-closing')
    }
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    const base = process.env['ELECTRON_RENDERER_URL']
    mainWindow.loadURL(isFirstLaunch() ? `${base}/#/setup` : base)
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'), {
      hash: isFirstLaunch() ? '/setup' : undefined
    })
  }
}

app.whenReady().then(async () => {
  electronApp.setAppUserModelId('com.travelcontentstudio.app')

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  try {
    await backendManager.start()
  } catch (err) {
    await backendManager.stop()
    const msg = err instanceof Error ? err.message : String(err)
    dialog.showErrorBox('Backend Startup Failed', `Could not start backend:\n\n${msg}`)
    app.quit()
    return
  }

  await ollamaManager.start()

  setupIpcHandlers(backendManager, ollamaManager)
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
}).catch((err) => {
  const msg = err instanceof Error ? err.message : String(err)
  dialog.showErrorBox('Startup Error', `Travel Content Studio failed to start:\n\n${msg}`)
  app.quit()
})

app.on('before-quit', async (e) => {
  if (!isQuitting) {
    isQuitting = true
    e.preventDefault()

    try {
      const port = backendManager.getPort()
      await fetch(`http://127.0.0.1:${port}/api/v1/system/shutdown`, { method: 'POST' }).catch(() => {})
      await new Promise((r) => setTimeout(r, 2000))
    } catch {
      // Backend may already be down
    }

    await ollamaManager.stop()
    await backendManager.stop()
    app.quit()
  }
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
