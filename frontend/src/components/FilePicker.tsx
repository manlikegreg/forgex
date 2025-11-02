import { useRef } from 'react'

export default function FilePicker({ onPick, label, placeholder, browseDir, browseFile, accept, onFileChosen, forceUpload, fileButtonLabel }: { onPick: (path: string) => void, label?: string, placeholder?: string, browseDir?: boolean, browseFile?: boolean, accept?: string, onFileChosen?: (file: File | null, url: string) => void, forceUpload?: boolean, fileButtonLabel?: string }) {
  const input = useRef<HTMLInputElement>(null)
  const hiddenFile = useRef<HTMLInputElement>(null)
  const hiddenDir = useRef<HTMLInputElement>(null)

  async function onBrowseDir() {
    // Prefer Electron bridge if available
    const anyWin = window as any
    if (anyWin.forgex?.pickDirectory) {
      const p = await anyWin.forgex.pickDirectory()
      if (p) { if (input.current) input.current.value = p; onPick(p) }
      return
    }
    // Fallback: browser directory picker (no absolute path)
    hiddenDir.current?.click()
  }

  async function onBrowseFile() {
    if (forceUpload) { hiddenFile.current?.click(); return }
    const anyWin = window as any
    if (anyWin.forgex?.pickFile) {
      const filters = accept ? [{ name: 'Allowed', extensions: accept.split(',').map((s: string) => s.trim().replace(/^\./, '')) }] : undefined
      const p = await anyWin.forgex.pickFile({ filters })
      if (p) {
        if (input.current) input.current.value = p; onPick(p)
        if (onFileChosen) onFileChosen(null, `file://${p}`)
      }
      return
    }
    hiddenFile.current?.click()
  }

  return (
    <div className="border-2 border-dashed border-gray-700 rounded p-6 text-center">
      <div className="mb-3 text-sm text-gray-400">{label || 'Enter a filesystem path'}</div>
      <div className="flex flex-wrap gap-2 items-center">
        <input ref={input} className="flex-1 min-w-[240px] bg-gray-900 border border-gray-700 rounded px-3 py-2" placeholder={placeholder || 'C:\\path\\to\\file or /path'} />
        {browseDir && (
          <button type="button" onClick={onBrowseDir} className="bg-gray-800 hover:bg-gray-700 px-3 py-2 rounded border border-gray-700">Browse Folder</button>
        )}
        {browseFile && (
          <button type="button" onClick={onBrowseFile} className="bg-gray-800 hover:bg-gray-700 px-3 py-2 rounded border border-gray-700">{fileButtonLabel || 'Browse File'}</button>
        )}
        <button onClick={() => input.current?.value && onPick(input.current.value)} className="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded">Use</button>
      </div>
      {/* Hidden fallbacks */}
      <input ref={hiddenFile} type="file" accept={accept} className="hidden" onChange={(e) => {
        const f = e.target.files?.[0]
        if (f) {
          const url = URL.createObjectURL(f)
          if (onFileChosen) onFileChosen(f, url)
          if (input.current) input.current.value = f.name
          onPick(input.current?.value || f.name)
        }
      }} />
      <input ref={hiddenDir} type="file" className="hidden" webkitdirectory="true" onChange={(e) => {
        const files = e.target.files
        if (files && files.length) {
          const first: any = files[0]
          const rel: string = first.webkitRelativePath || first.name
          const dir = rel.split('/')[0]
          if (input.current) input.current.value = dir
          onPick(input.current?.value || dir)
        }
      }} />
    </div>
  )
}
