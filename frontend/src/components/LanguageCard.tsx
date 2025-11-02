type Language = {
  id: string
  name: string
  description: string
}

export default function LanguageCard({ lang, active, onClick }: { lang: Language, active?: boolean, onClick?: ()=>void }) {
  return (
    <button onClick={onClick} className={`text-left rounded border ${active? 'border-blue-500':'border-gray-800'} p-4 hover:border-blue-400 transition` }>
      <div className="text-lg font-medium">{lang.name}</div>
      <div className="text-xs text-gray-400 mt-1">{lang.description}</div>
    </button>
  )
}
