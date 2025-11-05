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
  const [winHelperLog, setWinHelperLog] = useState(false)
  const [winHelperLogName, setWinHelperLogName] = useState('')

  // Protection options (Python / PyInstaller advanced)
  const [protectEnable, setProtectEnable] = useState(false)
  const [protectLevel, setProtectLevel] = useState<'basic'|'strong'|'max'>('basic')
  const [protectObfuscate, setProtectObfuscate] = useState(false)
  const [protectAntiDebug, setProtectAntiDebug] = useState(true)
  const [protectIntegrity, setProtectIntegrity] = useState(true)
  const [protectMaskLogs, setProtectMaskLogs] = useState(true)
  const [encryptEnv, setEncryptEnv] = useState(includeEnv)
  const [encMode, setEncMode] = useState<'inline'|'env'|'file'>('env')
  const [encPassphrase, setEncPassphrase] = useState('')
  const [encEnvVar, setEncEnvVar] = useState('FGX_ENV_KEY')
  const [encFilePath, setEncFilePath] = useState('')

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
      win_helper_log: winHelperLog || undefined,
      win_helper_log_name: winHelperLog ? (winHelperLogName || undefined) : undefined,
      // Privacy masking of logs at runtime
      privacy_mask_logs: protectMaskLogs || undefined,
      // PyInstaller advanced protection options
      pyinstaller: {
        protect: protectEnable ? {
          enable: true,
          level: protectLevel,
          obfuscate: protectObfuscate || undefined,
          anti_debug: protectAntiDebug || undefined,
          integrity_check: protectIntegrity || undefined,
          mask_logs: protectMaskLogs || undefined,
          encrypt_env: includeEnv && encryptEnv ? {
            enable: true,
            mode: encMode,
            passphrase: encMode === 'inline' ? (encPassphrase || undefined) : undefined,
            env_var: encMode === 'env' ? (encEnvVar || 'FGX_ENV_KEY') : undefined,
            file_path: encMode === 'file' ? (encFilePath || undefined) : undefined,
          } : undefined,
        } : undefined,
      },
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
          {winSmartHelper && (
            <div className="ml-5 mt-2 space-y-2">
              <div className="flex items-center gap-3">
                <input id="win_helper_log" type="checkbox" checked={winHelperLog} onChange={e=>setWinHelperLog(e.target.checked)} />
                <label htmlFor="win_helper_log">Log helper output to file</label>
              </div>
              {winHelperLog && (
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-400">Log filename</label>
                  <input className="bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="optional, e.g. MyApp.log" value={winHelperLogName} onChange={e=>setWinHelperLogName(e.target.value)} />
                </div>
              )}
            </div>
          )}
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
      {/* Protection options */}
      <div className="mt-4 border border-gray-800 rounded p-3">
        <div className="flex items-center gap-3">
          <input id="protect_en" type="checkbox" checked={protectEnable} onChange={e=>setProtectEnable(e.target.checked)} />
          <label htmlFor="protect_en">Protect build (Python only)</label>
          {protectEnable && (
            <select className="bg-gray-900 border border-gray-700 rounded px-2 py-1 ml-3" value={protectLevel} onChange={e=>setProtectLevel(e.target.value as any)}>
              <option value="basic">Basic</option>
              <option value="strong">Strong</option>
              <option value="max">Max</option>
            </select>
          )}
        </div>
        {protectEnable && (
          <div className="mt-3 space-y-3">
            <div className="flex items-center gap-3">
              <input id="prot_obf" type="checkbox" checked={protectObfuscate} onChange={e=>setProtectObfuscate(e.target.checked)} />
              <label htmlFor="prot_obf">Obfuscate code (PyArmor)</label>
            </div>
            <div className="flex items-center gap-3">
              <input id="prot_dbg" type="checkbox" checked={protectAntiDebug} onChange={e=>setProtectAntiDebug(e.target.checked)} />
              <label htmlFor="prot_dbg">Anti-debug</label>
            </div>
            <div className="flex items-center gap-3">
              <input id="prot_int" type="checkbox" checked={protectIntegrity} onChange={e=>setProtectIntegrity(e.target.checked)} />
              <label htmlFor="prot_int">Integrity check (.env package)</label>
            </div>
            <div className="flex items-center gap-3">
              <input id="prot_mask" type="checkbox" checked={protectMaskLogs} onChange={e=>setProtectMaskLogs(e.target.checked)} />
              <label htmlFor="prot_mask">Mask runtime logs</label>
            </div>
            <div className="mt-2">
              <div className="flex items-center gap-3">
                <input id="prot_envenc" type="checkbox" checked={encryptEnv} onChange={e=>setEncryptEnv(e.target.checked)} disabled={!includeEnv} />
                <label htmlFor="prot_envenc">Encrypt included .env</label>
                {!includeEnv && <span className="text-xs text-gray-500">(Enable "Include .env" above)</span>}
              </div>
              {includeEnv && encryptEnv && (
                <div className="ml-5 mt-2 space-y-2">
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-gray-400">Mode</label>
                    <select className="bg-gray-900 border border-gray-700 rounded px-2 py-1" value={encMode} onChange={e=>setEncMode(e.target.value as any)}>
                      <option value="env">Env var (default)</option>
                      <option value="file">File</option>
                      <option value="inline">Inline (dev only)</option>
                    </select>
                  </div>
                  {encMode === 'env' && (
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-gray-400">Env var name</label>
                      <input className="bg-gray-900 border border-gray-700 rounded px-2 py-1" value={encEnvVar} onChange={e=>setEncEnvVar(e.target.value)} />
                    </div>
                  )}
                  {encMode === 'file' && (
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-gray-400">Passphrase file path</label>
                      <input className="bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="e.g. .\\secret.key" value={encFilePath} onChange={e=>setEncFilePath(e.target.value)} />
                    </div>
                  )}
                  {encMode === 'inline' && (
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-gray-400">Passphrase</label>
                      <input type="password" className="bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="for development only" value={encPassphrase} onChange={e=>setEncPassphrase(e.target.value)} />
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <button onClick={handleStart} className="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded">Start Build</button>
    </div>
  )
}
