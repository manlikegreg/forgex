import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getBuildStatus } from '../utils/api'

const BASE = (import.meta.env.VITE_BACKEND_URL as string) || `http://127.0.0.1:${import.meta.env.VITE_BACKEND_PORT || 45555}`

export default function Result() {
  const { buildId } = useParams()
  const [status, setStatus] = useState<any>(null)
  const didAutoDownload = useRef(false)

  useEffect(() => {
    if (!buildId) return
    getBuildStatus(buildId).then(setStatus)
  }, [buildId])

  const files = useMemo(() => (status?.output_files || []) as string[], [status])

  useEffect(() => {
    if (!didAutoDownload.current && buildId && files.length) {
      // If Windows helper scripts are present, auto-download exe + ps1 + cmd; otherwise download first file
      const helperFiles = files.filter(f => /\.(ps1|cmd)$/i.test(f))
      const exeFiles = files.filter(f => /\.exe$/i.test(f))
      const toDownload = helperFiles.length && exeFiles.length
        ? [...exeFiles.slice(0,1), ...helperFiles]
        : [files[0]]
      let i = 0
      const trigger = () => {
        if (i >= toDownload.length) { didAutoDownload.current = true; return }
        const p = toDownload[i++]
        const name = p.split(/[\/\\]/).pop()!
        const url = `${BASE}/download/${buildId}/${encodeURIComponent(name)}`
        const a = document.createElement('a')
        a.href = url
        a.download = name
        a.style.display = 'none'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        setTimeout(trigger, 400) // slight delay to avoid browser blocking
      }
      trigger()
    }
  }, [buildId, files])

  return (
    <div className="space-y-4">
      <div className="text-sm text-gray-400">Build ID: {buildId}</div>
      {status && (
        <div className="text-xs text-gray-500">{status.language || '-'} · {status.start_command || '-'} · {status.output_type || '-'} · dir: {status.working_dir || '.'}</div>
      )}
      {files.length ? (
        <div>
          <div className="mb-2">Artifacts:</div>
          <ul className="list-disc pl-6 space-y-1">
            {files.map((p: string) => {
              const name = p.split(/[/\\]/).pop()!
              const url = `${BASE}/download/${buildId}/${encodeURIComponent(name)}`
              return (
                <li key={p} className="flex items-center gap-3">
                  <code className="flex-1 break-all">{p}</code>
                  <a className="text-blue-400 underline" href={url} download>Download</a>
                </li>
              )
            })}
          </ul>
        </div>
      ) : (
        <div>No artifacts yet.</div>
      )}
    </div>
  )
}
