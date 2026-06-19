import { app, BrowserWindow, shell } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { setupIpcHandlers } from './ipc-handlers'
import { BackendManager } from './backend-manager'
import { OllamaManager } from './ollama-manager'
import { isFirstLaunch } from './first-launch'

let mainWindow: BrowserWindow | null = null
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

  await backendManager.start()
  await ollamaManager.start()

  setupIpcHandlers(backendManager, ollamaManager)
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('before-quit', async () => {
  await backendManager.stop()
  await ollamaManager.stop()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
