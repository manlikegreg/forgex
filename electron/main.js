const { app, BrowserWindow, ipcMain, dialog } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args))

let mainWindow = null
let backendProc = null
const BACKEND_PORT = process.env.FORGEX_BACKEND_PORT || '45555'

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  })

  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'))
  }
}

function startBackend() {
  const py = process.env.FORGEX_PYTHON || 'python'
  const script = path.join(__dirname, '..', 'backend', 'main.py')
  backendProc = spawn(py, [script], { env: { ...process.env, FORGEX_BACKEND_PORT: BACKEND_PORT }, stdio: 'pipe' })
  backendProc.stdout.on('data', d => console.log('[backend]', d.toString()))
  backendProc.stderr.on('data', d => console.error('[backend]', d.toString()))
  backendProc.on('exit', code => console.log('backend exited', code))
}

app.whenReady().then(() => {
  startBackend()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  if (backendProc) {
    backendProc.kill('SIGTERM')
  }
})

// IPC: forward to HTTP backend
const BASE = `http://127.0.0.1:${BACKEND_PORT}`
ipcMain.handle('forgex:import', async (_e, payload) => {
  const fd = new (require('form-data'))();
  if (payload.path) fd.append('path', payload.path)
  const res = await fetch(`${BASE}/import-project`, { method: 'POST', body: fd })
  return res.json()
})

ipcMain.handle('forgex:start-build', async (_e, req) => {
  const res = await fetch(`${BASE}/start-build`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req) })
  return res.json()
})

ipcMain.handle('forgex:cancel-build', async (_e, { build_id }) => {
  const res = await fetch(`${BASE}/cancel-build`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ build_id }) })
  return res.json()
})

ipcMain.handle('forgex:status', async (_e, build_id) => {
  const res = await fetch(`${BASE}/build-status/${build_id}`)
  return res.json()
})

// Native pickers
ipcMain.handle('forgex:pick-dir', async () => {
  const res = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] })
  if (res.canceled || !res.filePaths || !res.filePaths[0]) return null
  return res.filePaths[0]
})

ipcMain.handle('forgex:pick-file', async (_e, opts) => {
  const res = await dialog.showOpenDialog(mainWindow, { properties: ['openFile'], filters: opts?.filters || undefined })
  if (res.canceled || !res.filePaths || !res.filePaths[0]) return null
  return res.filePaths[0]
})

// Logs: subscribe via WebSocket and forward to renderer
const WebSocket = require('ws')
const wsRegistry = new Map() // key: `${senderId}:${build_id}` -> ws

ipcMain.on('forgex:logs', (event, build_id) => {
  const key = `${event.sender.id}:${build_id}`
  // Close any existing ws for this key
  const existing = wsRegistry.get(key)
  if (existing) { try { existing.close() } catch {} wsRegistry.delete(key) }
  const ws = new WebSocket(`ws://127.0.0.1:${BACKEND_PORT}/ws/builds`)
  wsRegistry.set(key, ws)
  ws.on('open', () => { ws.send(JSON.stringify({ type: 'subscribe', build_id })) })
  ws.on('message', (data) => {
    try { const parsed = JSON.parse(data.toString()); event.sender.send(`forgex:logs:data:${build_id}`, parsed) } catch {}
  })
  const cleanup = () => {
    try { ws.close() } catch {}
    wsRegistry.delete(key)
  }
  ws.on('close', cleanup)
  ws.on('error', cleanup)
  // If renderer dies, clean up
  event.sender.once('destroyed', cleanup)
})

ipcMain.on('forgex:logs:unsubscribe', (event, build_id) => {
  if (build_id === '__all__') {
    const prefix = `${event.sender.id}:`
    for (const [key, ws] of Array.from(wsRegistry.entries())) {
      if (key.startsWith(prefix)) { try { ws.close() } catch {} wsRegistry.delete(key) }
    }
    return
  }
  const key = `${event.sender.id}:${build_id}`
  const ws = wsRegistry.get(key)
  if (ws) { try { ws.close() } catch {} wsRegistry.delete(key) }
})
