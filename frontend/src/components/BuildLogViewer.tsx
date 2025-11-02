import { useEffect, useMemo, useRef, useState } from 'react'
import type { LogEvent } from '@shared/types/build_types'

export default function BuildLogViewer({ logs }: { logs: LogEvent[] }) {
  const [level, setLevel] = useState<'info'|'warn'|'error'|'debug'|'all'>('all')
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(()=>{ endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [logs])
  const shown = useMemo(() => level==='all'? logs : logs.filter(l => l.level === level), [level, logs])
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm text-gray-400">Level</span>
        <select className="bg-gray-900 border border-gray-700 rounded px-2 py-1" value={level} onChange={e=>setLevel(e.target.value as any)}>
          <option value="all">All</option>
          <option value="info">Info</option>
          <option value="warn">Warn</option>
          <option value="error">Error</option>
          <option value="debug">Debug</option>
        </select>
        <div className="ml-auto text-xs text-gray-500">
          Note: Some error lines are normal during packaging; please wait for the build to finish.
        </div>
      </div>
      <div className="bg-black/40 border border-gray-800 rounded p-2 h-80 overflow-auto font-mono text-xs">
        {shown.map((l, i) => {
          const d = new Date(l.timestamp as any)
          const time = isNaN(d.getTime()) ? '-' : d.toLocaleTimeString()
          return (
            <div key={i} className={l.level==='error'? 'text-red-400': l.level==='warn'? 'text-yellow-300': l.level==='debug'? 'text-gray-400':'text-gray-200'}>
              [{time}] {l.level.toUpperCase()} {l.message}
            </div>
          )
        })}
        <div ref={endRef} />
      </div>
    </div>
  )
}
