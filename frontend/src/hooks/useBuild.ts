import { useCallback, useRef, useState } from 'react'
import type { LogEvent } from '@shared/types/build_types'

declare global { interface Window { forgex?: any } }

export default function useBuild() {
  const [logs, setLogs] = useState<LogEvent[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<any>(null)

  const subscribe = useCallback((buildId: string) => {
    if (window.forgex?.logsSubscribe && window.forgex?.onLogs) {
      // Ensure previous listeners are removed
      try { window.forgex.offLogs?.(buildId) } catch {}
      window.forgex.logsSubscribe(buildId)
      window.forgex.onLogs(buildId, (data: any) => {
        // Accept only proper log events
        if ((data && typeof data === 'object') && 'timestamp' in data && 'level' in data && 'message' in data) {
          setLogs((prev) => [...prev.slice(-2000), data as LogEvent])
        }
      })
      return
    }
    const url = (import.meta.env.VITE_BACKEND_WS || `ws://127.0.0.1:${import.meta.env.VITE_BACKEND_PORT || 45555}`) + '/ws/builds'
    function connect() {
      // Close any existing socket before reconnecting
      try { wsRef.current?.close() } catch {}
      const ws = new WebSocket(url)
      wsRef.current = ws
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'subscribe', build_id: buildId }))
      }
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          // Only accept events that look like LogEvent
          if (data && typeof data === 'object' && 'timestamp' in data && 'level' in data && 'message' in data) {
            setLogs(prev => [...prev.slice(-2000), data as LogEvent])
          }
        } catch {}
      }
      ws.onclose = () => {
        reconnectRef.current = setTimeout(connect, 1000)
      }
      ws.onerror = () => {
        try { ws.close() } catch {}
      }
    }
    connect()
  }, [])

  const close = useCallback(() => {
    if (reconnectRef.current) { clearTimeout(reconnectRef.current); reconnectRef.current = null }
    try { wsRef.current?.close() } catch {}
    wsRef.current = null
    // Electron bridge cleanup
    try { (window as any).forgex?.logsUnsubscribe?.('__all__') } catch {}
  }, [])

  return { logs, subscribe, close }
}
