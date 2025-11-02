const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('forgex', {
  import: (payload) => ipcRenderer.invoke('forgex:import', payload),
  startBuild: (req) => ipcRenderer.invoke('forgex:start-build', req),
  cancelBuild: (build_id) => ipcRenderer.invoke('forgex:cancel-build', { build_id }),
  status: (build_id) => ipcRenderer.invoke('forgex:status', build_id),
  logsSubscribe: (build_id) => ipcRenderer.send('forgex:logs', build_id),
  logsUnsubscribe: (build_id) => ipcRenderer.send('forgex:logs:unsubscribe', build_id),
  onLogs: (build_id, handler) => ipcRenderer.on(`forgex:logs:data:${build_id}`, (_e, data) => handler(data)),
  offLogs: (build_id) => ipcRenderer.removeAllListeners(`forgex:logs:data:${build_id}`),
  pickDirectory: () => ipcRenderer.invoke('forgex:pick-dir'),
  pickFile: (opts) => ipcRenderer.invoke('forgex:pick-file', opts),
})
