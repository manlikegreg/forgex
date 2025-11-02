import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import BuildLogViewer from '../components/BuildLogViewer'
import { getBuildStatus, cancelBuild } from '../utils/api'
import useBuild from '../hooks/useBuild'

export default function BuildProgress() {
  const { buildId } = useParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<any>({ status: 'queued' })
  const { logs, subscribe, close } = useBuild()

  useEffect(() => {
    if (!buildId) return
    subscribe(buildId)
    const t = setInterval(async () => {
      const s = await getBuildStatus(buildId)
      setStatus(s)
      if (s.status === 'success' || s.status === 'failed' || s.status === 'cancelled') {
        clearInterval(t)
        navigate(`/result/${buildId}`)
      }
    }, 1500)
    return () => { clearInterval(t); close() }
  }, [buildId])

  const percent = status.status === 'running' ? 60 : status.status === 'success' ? 100 : status.status === 'failed' ? 100 : 10

  async function onCancel() {
    if (!buildId) return
    await cancelBuild(buildId)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-400">Status: {status.status}</div>
        <button onClick={onCancel} className="text-sm bg-red-600 hover:bg-red-500 px-3 py-1 rounded">Cancel</button>
      </div>
      <div className="text-xs text-gray-500">{status.language || '-'} · {status.start_command || '-'} · dir: {status.working_dir || '.'}</div>
      <div className="bg-yellow-900/40 border border-yellow-600 text-yellow-200 font-semibold rounded px-3 py-2 text-sm">
        ⚠️ Note: Some error lines are normal during packaging; please wait for the build to finish.
      </div>
      <div className="w-full bg-gray-800 rounded h-3 overflow-hidden">
        <div className="bg-green-500 h-3" style={{ width: `${percent}%` }} />
      </div>
      <BuildLogViewer logs={logs} />
    </div>
  )
}
