import { useEffect, useState } from 'react'
import FilePicker from '../components/FilePicker'
import OutputSelector from '../components/OutputSelector'
import { startBuild, getBuildHistory, uploadProject } from '../utils/api'
import { Link, useNavigate } from 'react-router-dom'
import { LANGUAGES } from '@shared/constants/languages'
import JSZip from 'jszip'

export default function Home() {
  const [projectPath, setProjectPath] = useState('')
  const [workingDir, setWorkingDir] = useState('.')
  const [language, setLanguage] = useState('python')
  const [startCommand, setStartCommand] = useState('')
  const [outputType, setOutputType] = useState<'exe'|'app'|'elf'>('exe')
  const [targetOS, setTargetOS] = useState<'windows'|'linux'|'macos'>('windows')
  const [outputName, setOutputName] = useState('')
  const [includeEnv, setIncludeEnv] = useState(true)
  const [verbose, setVerbose] = useState(false)
  const [pauseOnExit, setPauseOnExit] = useState(false)
  const [pauseSeconds, setPauseSeconds] = useState<number>(5)
  const [winAutoStart, setWinAutoStart] = useState(false)
  const [autostartMethod, setAutostartMethod] = useState<'task'|'startup'>('task')
  const [winSmartHelper, setWinSmartHelper] = useState(false)
  const [winHelperLog, setWinHelperLog] = useState(false)
  const [winHelperLogName, setWinHelperLogName] = useState('')
  const [signEnable, setSignEnable] = useState(false)
  const [signCert, setSignCert] = useState('')
  const [signPwd, setSignPwd] = useState('')
  const [signTS, setSignTS] = useState('http://timestamp.digicert.com')
  const [iconPath, setIconPath] = useState('')
  const [iconPreview, setIconPreview] = useState<string | null>(null)
  const [history, setHistory] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  // PyInstaller simple options
  const [pyiNoConsole, setPyiNoConsole] = useState(false)
  const [maskRuntimeLogs, setMaskRuntimeLogs] = useState(false)
  const [pyiHiddenImports, setPyiHiddenImports] = useState('')
  const [pyiPaths, setPyiPaths] = useState('')
  const [pyiAddData, setPyiAddData] = useState('')
  const [pyiDebug, setPyiDebug] = useState<'none'|'minimal'|'all'>('none')
  const [pyiNoUpx, setPyiNoUpx] = useState(false)
  const [pyiCollectAll, setPyiCollectAll] = useState('')
  const [pyiCollectData, setPyiCollectData] = useState('')
  const [pyiRuntimeHooks, setPyiRuntimeHooks] = useState('')
  const [pyiAdditionalHooksDir, setPyiAdditionalHooksDir] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadDone, setUploadDone] = useState(false)
  const [uploadErr, setUploadErr] = useState<string | null>(null)
  const [uploadNames, setUploadNames] = useState<string[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [uploadPhase, setUploadPhase] = useState<'idle'|'zipping'|'uploading'|'done'|'error'>('idle')
  const [zipProgress, setZipProgress] = useState<{done:number,total:number}>({done:0,total:0})
  // Protection options (Python / PyInstaller advanced)
  const [protectEnable, setProtectEnable] = useState(false)
  const [protectLevel, setProtectLevel] = useState<'basic'|'strong'|'max'>('basic')
  const [protectObfuscate, setProtectObfuscate] = useState(false)
  const [protectAntiDebug, setProtectAntiDebug] = useState(true)
  const [protectIntegrity, setProtectIntegrity] = useState(true)
  const [encryptEnv, setEncryptEnv] = useState(includeEnv)
  const [encMode, setEncMode] = useState<'inline'|'env'|'file'>('env')
  const [encPassphrase, setEncPassphrase] = useState('')
  const [encEnvVar, setEncEnvVar] = useState('FGX_ENV_KEY')
  const [encFilePath, setEncFilePath] = useState('')

  const navigate = useNavigate()

  useEffect(() => { getBuildHistory().then(setHistory) }, [])

  async function onStart() {
    setError(null)
    if (!language || !startCommand) {
      setError('Language and Start Command are required')
      return
    }
    if (!projectPath) {
      setError('Please upload a project (or select a folder in the desktop app)')
      return
    }
    if (uploading) {
      setError('Wait for upload to finish before starting the build')
      return
    }
    const pyi: any = {}
    if (pyiNoConsole) pyi.noconsole = true
    const toList = (s: string) => s.split(',').map(x=>x.trim()).filter(Boolean)
    const toLines = (s: string) => s.split('\n').map(x=>x.trim()).filter(Boolean)
    const addData = toLines(pyiAddData).map(line=>{
      const m = line.split(';')
      return m.length===2? { src: m[0], dest: m[1] }: null
    }).filter(Boolean)
    if (addData.length) pyi.add_data = addData
    const hi = toList(pyiHiddenImports); if (hi.length) pyi.hidden_imports = hi
    const pathsList = toList(pyiPaths); if (pathsList.length) pyi.paths = pathsList
    if (pyiDebug !== 'none') pyi.debug = pyiDebug
    if (pyiNoUpx) pyi.noupx = true
    const ca = toList(pyiCollectAll); if (ca.length) pyi.collect_all = ca
    const cd = toList(pyiCollectData); if (cd.length) pyi.collect_data = cd
    const rh = toList(pyiRuntimeHooks); if (rh.length) pyi.runtime_hooks = rh
    const ahd = toList(pyiAdditionalHooksDir); if (ahd.length) pyi.additional_hooks_dir = ahd

    // Protection block
    if (protectEnable) {
      const enc = includeEnv && encryptEnv ? {
        enable: true,
        mode: encMode,
        passphrase: encMode === 'inline' ? (encPassphrase || undefined) : undefined,
        env_var: encMode === 'env' ? (encEnvVar || 'FGX_ENV_KEY') : undefined,
        file_path: encMode === 'file' ? (encFilePath || undefined) : undefined,
      } : undefined
      pyi.protect = {
        enable: true,
        level: protectLevel,
        obfuscate: protectObfuscate || undefined,
        anti_debug: protectAntiDebug || undefined,
        integrity_check: protectIntegrity || undefined,
        mask_logs: maskRuntimeLogs || undefined,
        encrypt_env: enc,
      }
    }

    const req = {
      project_path: projectPath,
      working_dir: workingDir,
      language,
      start_command: startCommand,
      output_type: outputType,
      include_env: includeEnv,
      target_os: targetOS,
      output_name: outputName || undefined,
      icon_path: iconPath || null,
      extra_files: [],
      pyinstaller: Object.keys(pyi).length? pyi : undefined,
      privacy_mask_logs: maskRuntimeLogs || undefined,
      pause_on_exit: pauseOnExit,
      pause_on_exit_seconds: pauseOnExit ? pauseSeconds : undefined,
      win_autostart: winAutoStart || undefined,
      autostart_method: winAutoStart ? autostartMethod : undefined,
      code_sign: signEnable ? { enable: true, cert_path: signCert, cert_password: signPwd || undefined, timestamp_url: signTS || undefined } : undefined,
      win_smartscreen_helper: winSmartHelper || undefined,
      win_helper_log: winHelperLog || undefined,
      win_helper_log_name: winHelperLog ? (winHelperLogName || undefined) : undefined,
      verbose,
    } as any
    const res = await startBuild(req)
    navigate(`/progress/${res.build_id}`)
  }

  type UploadItem = File | { file: File, path: string }

  async function doUpload(items: UploadItem[]) {
    try {
      setUploadErr(null); setUploadDone(false); setUploading(true); setUploadPhase('idle'); setZipProgress({done:0,total:0})
      const normalized = items.map((it:any) => ('file' in it ? { file: it.file, path: it.path } : { file: it as File, path: (it as any).webkitRelativePath || (it as File).name }))
      setUploadNames(normalized.map(n => n.path))
      const fd = new FormData()
      if (normalized.length === 1 && normalized[0].file.name.toLowerCase().endsWith('.zip')) {
        // Upload zip as-is
        setUploadPhase('uploading')
        fd.append('zip', normalized[0].file)
      } else {
        // Client-side zip to avoid multipart field limits
        setUploadPhase('zipping')
        const zip = new JSZip()
        // Filter out very large or unwanted folders by name (basic): node_modules, .git, __pycache__, .venv, venv
        const shouldSkip = (p: string) => /(^|\/)node_modules(\/|$)|(^|\/)\.git(\/|$)|(^|\/)__pycache__(\/|$)|(^|\/)\.venv(\/|$)|(^|\/)venv(\/|$)/.test(p)
        const files = normalized.filter(n => !shouldSkip(n.path))
        setZipProgress({done:0,total:files.length})
        let i = 0
        for (const n of files) {
          // Ensure forward slashes in zip paths
          const zp = n.path.replace(/\\/g, '/').replace(/^\/+/, '')
          zip.file(zp, n.file)
          i++
          if (i % 25 === 0 || i === files.length) setZipProgress({done:i,total:files.length})
        }
        const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 6 } }, (meta) => {
          // Optional: progress callback; we already track file count above
        })
        setUploadPhase('uploading')
        fd.append('zip', new File([blob], 'project.zip', { type: 'application/zip' }))
      }
      const res = await uploadProject(fd)
      if (res?.project_path) {
        setProjectPath(res.project_path)
        setUploadDone(true)
        setUploadPhase('done')
      } else {
        setUploadErr('Upload failed')
        setUploadPhase('error')
      }
    } catch (e: any) {
      setUploadErr('Upload failed')
      setUploadPhase('error')
    } finally {
      setUploading(false)
    }
  }

  async function collectDropped(e: any): Promise<{ file: File, path: string }[]> {
    const dt = e.dataTransfer
    if (!dt) return []
    const items = Array.from(dt.items || []) as any[]
    const supportsEntries = items.length && typeof items[0].webkitGetAsEntry === 'function'
    if (!supportsEntries) {
      return Array.from(dt.files || []).map(f => ({ file: f, path: (f as any).webkitRelativePath || f.name }))
    }
    const results: { file: File, path: string }[] = []

    const readFile = (entry: any, path: string) => new Promise<void>((resolve) => {
      entry.file((file: File) => { results.push({ file, path: path ? `${path}/${file.name}` : file.name }); resolve() })
    })
    const readDir = async (entry: any, path: string) => {
      const reader = entry.createReader()
      const readEntries = (): Promise<any[]> => new Promise(res => reader.readEntries(res))
      let entries: any[] = []
      do {
        entries = await readEntries()
        for (const ent of entries) {
          if (ent.isFile) await readFile(ent, path)
          else if (ent.isDirectory) await readDir(ent, path ? `${path}/${ent.name}` : ent.name)
        }
      } while (entries.length)
    }

    for (const it of items) {
      const entry = it.webkitGetAsEntry()
      if (!entry) continue
      if (entry.isFile) await readFile(entry, '')
      else if (entry.isDirectory) await readDir(entry, entry.name)
    }
    return results
  }

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="mb-2 text-sm text-gray-400">Project</div>
          {/* Upload section */}
          <div className="border border-dashed border-gray-700 rounded p-4">
            <div className="text-sm text-gray-300 mb-2">Upload file(s) or .zip</div>
            <div className="text-xs text-gray-400 mb-3">Drop files here, or use the buttons. For folders, we zip client-side to improve reliability and then upload.</div>
            <div 
              onDragEnter={()=>setDragOver(true)} 
              onDragLeave={()=>setDragOver(false)} 
              onDragOver={e=>{e.preventDefault()}} 
              onDrop={async e=>{
                e.preventDefault(); setDragOver(false)
                const items = await collectDropped(e)
                if (!items.length) return
                await doUpload(items)
              }} 
              className={`rounded p-6 text-center ${dragOver? 'bg-blue-900/30 border border-blue-500 text-blue-200 animate-pulse':'bg-black/20 text-gray-400'}`}>
              {uploading ? (
                uploadPhase === 'zipping' ? (
                  <div className="flex items-center justify-center gap-2">
                    <div className="h-4 w-4 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin"></div>
                    <div>Zipping {zipProgress.done}/{zipProgress.total} files…</div>
                  </div>
                ) : uploadPhase === 'uploading' ? (
                  <div className="flex items-center justify-center gap-2">
                    <div className="h-4 w-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"></div>
                    <div>Uploading {uploadNames.slice(0,3).join(', ')}{uploadNames.length>3?` +${uploadNames.length-3}`:''} …</div>
                  </div>
                ) : (
                  <div className="flex items-center justify-center gap-2">
                    <div className="h-4 w-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"></div>
                    <div>Processing…</div>
                  </div>
                )
              ) : uploadDone ? (
                <div className="text-green-400">Uploaded ✓ {uploadNames.slice(0,3).join(', ')}{uploadNames.length>3?` +${uploadNames.length-3}`:''}</div>
              ) : (
                <>Drag & drop files or .zip here</>
              )}
            </div>
            {uploadErr && <div className="text-red-400 text-xs mt-2">{uploadErr}</div>}
            <div className="flex flex-wrap gap-2 mt-3">
              <label className="bg-gray-800 hover:bg-gray-700 px-3 py-2 rounded border border-gray-700 cursor-pointer">
                Upload file(s) or .zip
                <input type="file" multiple className="hidden" onChange={async e=>{
                  const files = Array.from(e.target.files || [])
                  if (!files.length) return
                  await doUpload(files)
                }} />
              </label>
              <label className="bg-gray-800 hover:bg-gray-700 px-3 py-2 rounded border border-gray-700 cursor-pointer">
                Upload folder (zips then uploads)
                <input type="file" className="hidden" webkitdirectory="true" onChange={async e=>{
                  const files = Array.from(e.target.files || [])
                  if (!files.length) return
                  await doUpload(files)
                }} />
              </label>
            </div>
          </div>
          <div>
            <label className="text-sm text-gray-400" title="Relative path inside project where commands run">Working directory</label>
            <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-3 py-2" value={workingDir} onChange={e=>setWorkingDir(e.target.value)} />
          </div>
          <div>
            <label className="text-sm text-gray-400" title="Upload an app icon (.ico/.icns/.png); it will be sent to the builder">Icon file</label>
            <FilePicker 
              onPick={(p)=>{ setIconPath(p) }} 
              label="Icon file"
              placeholder="Upload .ico/.icns/.png"
              browseFile 
              accept=".ico,.icns,.png" 
              forceUpload 
              fileButtonLabel="Upload Icon"
              onFileChosen={async (f, url)=>{ 
                setIconPreview(url)
                if (f) {
                  const fd = new FormData();
                  fd.append('files', f, f.name)
                  try {
                    const res = await uploadProject(fd)
                    const base = (res as any).project_path as string
                    const sep = base.includes('\\\\') || base.includes('\\') ? '\\\\' : '/'
                    setIconPath(`${base}${sep}${f.name}`)
                  } catch {
                    setError('Icon upload failed')
                  }
                }
              }} 
            />
            {iconPreview && (
              <div className="mt-2">
                <img src={iconPreview} alt="icon preview" className="w-12 h-12 object-contain inline-block border border-gray-800 rounded" />
              </div>
            )}
          </div>
          <div>
            <div className="flex items-center gap-3">
              <input id="env" type="checkbox" checked={includeEnv} onChange={e=>setIncludeEnv(e.target.checked)} />
              <label htmlFor="env" title="Include a .env file in the packaged app">Include .env</label>
            </div>
            <div className="text-[11px] text-gray-500 mt-1">
              If included: it loads .env from the embedded bundle. If not included: it looks for a .env file in the same folder as the .exe and loads it automatically if present.
            </div>
            {language === 'python' && (
              <div className="mt-3 flex items-center gap-3">
                <input id="pause" type="checkbox" checked={pauseOnExit} onChange={e=>setPauseOnExit(e.target.checked)} />
                <label htmlFor="pause" title="Keeps the console open a moment so you can read errors">Pause on exit (Python)</label>
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
            )}
            <div className="mt-3 flex items-center gap-3">
              <input id="verbose" type="checkbox" checked={verbose} onChange={e=>setVerbose(e.target.checked)} />
              <label htmlFor="verbose" title="Include debug logs from the backend build process">Verbose logs</label>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <input id="mask_logs" type="checkbox" checked={maskRuntimeLogs} onChange={e=>setMaskRuntimeLogs(e.target.checked)} />
              <label htmlFor="mask_logs" title="Mask runtime log messages inside the packaged app (privacy)">Mask runtime logs (privacy)</label>
              {!pyiNoConsole && <span className="text-[11px] text-gray-500">Works best with --noconsole</span>}
            </div>
            {outputType === 'exe' && (
              <>
                <div className="mt-3 flex items-center gap-3">
                  <input id="win_auto" type="checkbox" checked={winAutoStart} onChange={e=>setWinAutoStart(e.target.checked)} />
                  <label htmlFor="win_auto" title="Registers autostart on user logon">Auto-start on Windows (at logon)</label>
                  {winAutoStart && (
                    <select className="bg-gray-900 border border-gray-700 rounded px-2 py-1" value={autostartMethod} onChange={e=>setAutostartMethod(e.target.value as any)}>
                      <option value="task">Task Scheduler</option>
                      <option value="startup">Startup Folder</option>
                    </select>
                  )}
                </div>
                <div className="mt-3 flex items-center gap-3">
                  <input id="win_helper" type="checkbox" checked={winSmartHelper} onChange={e=>setWinSmartHelper(e.target.checked)} />
                  <label htmlFor="win_helper" title="Generate a helper script (PowerShell) to launch the app. Not a guarantee to bypass SmartScreen.">Windows SmartScreen helper script</label>
                </div>
                <div className="mt-3 flex items-center gap-3">
                  <input id="win_helper" type="checkbox" checked={winSmartHelper} onChange={e=>setWinSmartHelper(e.target.checked)} />
                  <label htmlFor="win_helper" title="Generate a helper script (PowerShell) to launch the app. Not a guarantee to bypass SmartScreen.">Windows SmartScreen helper script</label>
                </div>
                {winSmartHelper && (
                  <div className="mt-2 ml-5 space-y-2">
                    <div className="flex items-center gap-3">
                      <input id="win_helper_log" type="checkbox" checked={winHelperLog} onChange={e=>setWinHelperLog(e.target.checked)} />
                      <label htmlFor="win_helper_log" title="Write helper output to a .log file next to the scripts">Log helper output to file</label>
                    </div>
                    {winHelperLog && (
                      <div className="flex items-center gap-2">
                        <label className="text-xs text-gray-400">Log filename</label>
                        <input className="bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="optional, e.g. MyApp.log" value={winHelperLogName} onChange={e=>setWinHelperLogName(e.target.value)} />
                        <span className="text-[11px] text-gray-500">Default: Run-MyApp.log</span>
                      </div>
                    )}
                  </div>
                )}
                <div className="mt-3 border border-gray-800 rounded p-3">
                  <div className="flex items-center gap-3">
                    <input id="sign_en" type="checkbox" checked={signEnable} onChange={e=>setSignEnable(e.target.checked)} />
                    <label htmlFor="sign_en" title="Sign the built executable with your code signing certificate">Code sign (Windows)</label>
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
          </div>
        </div>
        <div className="space-y-4">
          <div className="mb-2 text-sm text-gray-400">Configuration</div>
          <div>
            <label className="text-sm text-gray-400">Language</label>
            <select className="mt-1 bg-gray-900 border border-gray-700 rounded px-3 py-2 w-full" value={language} onChange={e=>setLanguage(e.target.value)}>
              {LANGUAGES.map(l => (<option key={l.id} value={l.id}>{l.name}</option>))}
            </select>
          </div>
          <div>
            <label className="text-sm text-gray-400" title="How you start your app from terminal, e.g. 'python app.py'">Start command</label>
            <input
              className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-3 py-2"
              placeholder="e.g. python main.py, uvicorn main:app --host 0.0.0.0 --port 8000, node index.js"
              value={startCommand}
              onChange={e=>setStartCommand(e.target.value)}
            />
          </div>
          <div className="mb-2 text-sm text-gray-400">Target OS</div>
          <div className="flex gap-2 mb-3">
            {(['windows','macos','linux'] as const).map(os => (
              <button key={os}
                type="button"
                className={`px-3 py-1 rounded text-sm border ${targetOS===os? 'bg-blue-600 border-blue-500' : 'bg-gray-900 border-gray-700 hover:bg-gray-800'}`}
                onClick={()=>setTargetOS(os)}
                title="Select the target operating system for packaging/runtime tweaks"
              >{os}</button>
            ))}
          </div>
          <OutputSelector value={outputType} onChange={setOutputType} />

          <div>
            <label className="text-sm text-gray-400" title="Name of the output file (without extension); leave blank to use project name">Output filename</label>
            <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-3 py-2" placeholder="myapp" value={outputName} onChange={e=>setOutputName(e.target.value)} />
            <div className="text-[11px] text-gray-500 mt-1">Extension is added automatically (e.g., .exe on Windows).</div>
          </div>

          {language === 'python' && (
            <div className="mt-2 border border-gray-800 rounded p-3 bg-black/30">
              <button type="button" className="w-full flex items-center justify-between mb-2 bg-gray-900/40 hover:bg-gray-900/60 border border-gray-800 rounded px-3 py-2" onClick={()=>setShowAdvanced(s=>!s)} aria-expanded={showAdvanced} aria-controls="pyi-advanced">
                <span className="text-sm text-gray-300">PyInstaller options</span>
                <svg className={`h-4 w-4 text-gray-400 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.24a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.08z" clipRule="evenodd"/></svg>
              </button>
              <div id="pyi-advanced" className={showAdvanced ? '' : 'hidden'}>
                <div className="flex items-center gap-2 mb-2">
                  <input id="pyi_nc" type="checkbox" checked={pyiNoConsole} onChange={e=>setPyiNoConsole(e.target.checked)} />
                  <label htmlFor="pyi_nc" title="Do not open a console window for GUI apps">--noconsole (GUI app)</label>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-gray-400" title="Add modules PyInstaller may miss; comma-separated">hidden-imports (comma)</label>
                    <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="pkg.mod, another.mod" value={pyiHiddenImports} onChange={e=>setPyiHiddenImports(e.target.value)} />
                    <div className="text-[11px] text-gray-500 mt-1">Extra modules to include, e.g., pkg.mod, another.mod</div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-400" title="Additional import search paths; comma-separated">paths (comma)</label>
                    <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="src, lib" value={pyiPaths} onChange={e=>setPyiPaths(e.target.value)} />
                    <div className="text-[11px] text-gray-500 mt-1">Like -p option; where to look for imports</div>
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-xs text-gray-400" title="Include extra files; format 'SRC;DEST' per line">add-data (one per line, SRC;DEST)</label>
                    <textarea className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 h-16" placeholder="config.ini;." value={pyiAddData} onChange={e=>setPyiAddData(e.target.value)} />
                    <div className="text-[11px] text-gray-500 mt-1">Example: assets/logo.png;assets</div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-400" title="Amount of debug output at runtime">debug</label>
                    <select className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1" value={pyiDebug} onChange={e=>setPyiDebug(e.target.value as any)}>
                      <option value="none">none</option>
                      <option value="minimal">minimal</option>
                      <option value="all">all</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2 mt-6">
                    <input id="pyi_noupx" type="checkbox" checked={pyiNoUpx} onChange={e=>setPyiNoUpx(e.target.checked)} />
                    <label htmlFor="pyi_noupx" title="Do not compress binaries with UPX">--noupx</label>
                  </div>
                  <div>
                    <label className="text-xs text-gray-400" title="Collect all data and binaries from packages">collect-all (comma pkgs)</label>
                    <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="pkg1, pkg2" value={pyiCollectAll} onChange={e=>setPyiCollectAll(e.target.value)} />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400" title="Collect only data files from packages">collect-data (comma pkgs)</label>
                    <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="pkg1, pkg2" value={pyiCollectData} onChange={e=>setPyiCollectData(e.target.value)} />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400" title="Python scripts that run before your app starts; comma-separated paths">runtime-hooks (comma paths)</label>
                    <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="hooks/startup.py" value={pyiRuntimeHooks} onChange={e=>setPyiRuntimeHooks(e.target.value)} />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400" title="Folders containing hook-*.py files">additional-hooks-dir (comma)</label>
                    <input className="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-1" placeholder="hooks" value={pyiAdditionalHooksDir} onChange={e=>setPyiAdditionalHooksDir(e.target.value)} />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Protection options */}
          {language === 'python' && (
            <div className="mt-2 border border-gray-800 rounded p-3 bg-black/30">
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
                  <div className="mt-2">
                    <div className="flex items-center gap-3">
                      <input id="prot_envenc" type="checkbox" checked={encryptEnv} onChange={e=>setEncryptEnv(e.target.checked)} disabled={!includeEnv} />
                      <label htmlFor="prot_envenc">Encrypt included .env</label>
                      {!includeEnv && <span className="text-xs text-gray-500">(Enable \"Include .env\" above)</span>}
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
          )}

          <div>
            <button onClick={onStart} className="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded disabled:opacity-50" disabled={!language || !startCommand}>Start Build</button>
            {projectPath && <div className="text-xs text-gray-500 mt-2 break-all">Using project: {projectPath}</div>}
            {error && <div className="text-red-400 text-sm mt-2">{error}</div>}
          </div>
        </div>
      </div>
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm text-gray-400">History</div>
          <button
            className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 px-2 py-1 rounded"
            onClick={async ()=>{ try { (await import('../utils/api')).clearHistory().then(()=>setHistory([])) } catch {} }}
            title="Clear all build history"
          >Clear</button>
        </div>
        <div className="space-y-1">
          {history.map((h) => (
            <div key={h.build_id} className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded px-3 py-2 text-sm">
              <div>
                <div className="font-mono text-xs">{h.build_id}</div>
                <div className="text-gray-400">{h.status}</div>
                <div className="text-gray-500 text-xs">{h.language || '-'} · {h.start_command || '-'}</div>
              </div>
              <Link className="text-blue-400" to={`/result/${h.build_id}`}>Open</Link>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
