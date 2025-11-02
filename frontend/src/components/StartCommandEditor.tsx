import { useMemo } from 'react'
import { PRESETS } from '@shared/constants/languages'

export default function StartCommandEditor({ value, onChange, language }: { value: string, onChange: (v: string)=>void, language: string }) {
  const presets = useMemo(() => {
    return PRESETS[language]?.frameworks || []
  }, [language])

  return (
    <div>
      <label className="text-sm text-gray-400">Start command</label>
      <div className="mt-1 flex gap-2">
        <input
          className="flex-1 bg-gray-900 border border-gray-700 rounded px-3 py-2"
          value={value}
          onChange={e=>onChange(e.target.value)}
          placeholder="e.g. python main.py, uvicorn main:app --host 0.0.0.0 --port 8000, node index.js"
        />
        <div className="relative">
          <select className="bg-gray-900 border border-gray-700 rounded px-3 py-2" onChange={e=>onChange((e.target as any).value)}>
            <option value="">Presets</option>
            {presets.map((p: any) => (
              <option key={p.name} value={p.command}>{p.name}</option>
            ))}
          </select>
        </div>
      </div>
      <p className="mt-1 text-xs text-gray-500">Examples: python app.py · uvicorn main:app --host 0.0.0.0 --port 8000 · node server.js</p>
    </div>
  )
}
