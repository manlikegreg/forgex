import { useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useMemo, useState } from 'react'
import StartCommandEditor from '../components/StartCommandEditor'
import OutputSelector from '../components/OutputSelector'
import { startBuild } from '../utils/api'

export default function Configure() {
  const { state } = useLocation() as any
  const navigate = useNavigate()
  const [workingDir, setWorkingDir] = useState(state?.working_dir || '.')
  const [startCommand, setStartCommand] = useState(state?.detected?.suggested_command || '')
const [outputType, setOutputType] = useState<'exe'|'app'|'elf'>('exe')
  const [includeEnv, setIncludeEnv] = useState(true)
  const [iconPath, setIconPath] = useState<string | null>(null)
  const [extraFiles, setExtraFiles] = useState<string[]>([])
  const [language, setLanguage] = useState<string>(state?.detected?.language || 'auto')
  const [pauseOnExit, setPauseOnExit] = useState(false)
  const [pauseSeconds, setPauseSeconds] = useState<number>(5)
  const [winAutoStart, setWinAutoStart] = useState(false)
  const [autostartMethod, setAutostartMethod] = useState<'task'|'startup'>('task')
  const [signEnable, setSignEnable] = useState(false)
  const [signCert, setSignCert] = useState('')
  const [signPwd, setSignPwd] = useState('')
  const [signTS, setSignTS] = useState('http://timestamp.digicert.com')
  const [winSmartHelper, setWinSmartHelper] = useState(false)

  async function handleStart() {
    const req = {
      project_path: state?.project_path,
      working_dir: workingDir,
      language,
      start_command: startCommand,
      output_type: outputType,
      include_env: includeEnv,
      icon_path: iconPath,
      extra_files: extraFiles,
      pause_on_exit: pauseOnExit,
      pause_on_exit_seconds: pauseOnExit ? pauseSeconds : undefined,
      win_autostart: winAutoStart || undefined,
      autostart_method: winAutoStart ? autostartMethod : undefined,
      code_sign: signEnable ? { enable: true, cert_path: signCert, cert_password: signPwd || undefined, timestamp_url: signTS || undefined } : undefined,
      win_smartscreen_helper: winSmartHelper || undefined,
    }
    const res = await startBuild(req as any)
    navigate(`/progress/${res.build_id}`, { state: { build_id: res.build_id } })
  }

  return (
    <div className="space-y-6">
      <div>
        <label className="text-sm text-gray-400">Working directory</label>
        <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-3 py-2" value={workingDir} onChange={e=>setWorkingDir(e.target.value)} />
      </div>
      <StartCommandEditor value={startCommand} onChange={setStartCommand} language={language} />
      <OutputSelector value={outputType} onChange={setOutputType} />
      <div className="flex items-center gap-3">
        <input id="env" type="checkbox" checked={includeEnv} onChange={e=>setIncludeEnv(e.target.checked)} />
        <label htmlFor="env">Include .env</label>
      </div>
      <div className="flex items-center gap-3">
        <input id="pause" type="checkbox" checked={pauseOnExit} onChange={e=>setPauseOnExit(e.target.checked)} />
        <label htmlFor="pause">Pause on exit (Python)</label>
        {pauseOnExit && (
          <select className="bg-gray-900 border border-gray-700 rounded px-2 py-1"
                  value={String(pauseSeconds)}
                  onChange={e=>setPauseSeconds(parseInt(e.target.value, 10) || 5)}>
            {[2,5,10,30,60].map(s => (
              <option key={s} value={s}>{s}s</option>
            ))}
          </select>
        )}
      </div>
      {outputType === 'exe' && (
        <>
          <div className="flex items-center gap-3">
            <input id="win_auto" type="checkbox" checked={winAutoStart} onChange={e=>setWinAutoStart(e.target.checked)} />
            <label htmlFor="win_auto">Auto-start on Windows (at logon)</label>
            {winAutoStart && (
              <select className="bg-gray-900 border border-gray-700 rounded px-2 py-1" value={autostartMethod} onChange={e=>setAutostartMethod(e.target.value as any)}>
                <option value="task">Task Scheduler</option>
                <option value="startup">Startup Folder</option>
              </select>
            )}
          </div>
          <div className="flex items-center gap-3">
            <input id="win_helper" type="checkbox" checked={winSmartHelper} onChange={e=>setWinSmartHelper(e.target.checked)} />
            <label htmlFor="win_helper" title="Generate a helper script (PowerShell) to launch the app. Not a guarantee to bypass SmartScreen.">Windows SmartScreen helper script</label>
          </div>
          <div className="mt-3 border border-gray-800 rounded p-3">
            <div className="flex items-center gap-3">
              <input id="sign_en" type="checkbox" checked={signEnable} onChange={e=>setSignEnable(e.target.checked)} />
              <label htmlFor="sign_en">Code sign (Windows)</label>
            </div>
            {signEnable && (
              <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400">Certificate (.pfx)</label>
                  <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="C:\\path\\to\\cert.pfx" value={signCert} onChange={e=>setSignCert(e.target.value)} />
                </div>
                <div>
                  <label className="text-xs text-gray-400">Password</label>
                  <input type="password" className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="••••••" value={signPwd} onChange={e=>setSignPwd(e.target.value)} />
                </div>
                <div className="md:col-span-2">
                  <label className="text-xs text-gray-400">Timestamp URL</label>
                  <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1" value={signTS} onChange={e=>setSignTS(e.target.value)} />
                </div>
              </div>
            )}
          </div>
        </>
      )}
      <button onClick={handleStart} className="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded">Start Build</button>
    </div>
  )
}
