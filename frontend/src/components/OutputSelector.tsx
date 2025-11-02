type OutputType = 'exe'|'app'|'elf'

export default function OutputSelector({ value, onChange }: { value: OutputType, onChange: (v: OutputType)=>void }) {
  return (
    <div>
      <label className="text-sm text-gray-400">Output type</label>
      <select className="mt-1 bg-gray-900 border border-gray-700 rounded px-3 py-2" value={value} onChange={e=>onChange(e.target.value as OutputType)}>
        <option value="exe">Windows (.exe)</option>
        <option value="elf">Linux (ELF binary)</option>
        <option value="app">macOS (.app bundle)</option>
      </select>
    </div>
  )
}
