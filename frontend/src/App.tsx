import { Outlet, Link, useLocation } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'

export default function App() {
  const loc = useLocation()
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-800 p-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">ForgeX — Universal Project Bundler</h1>
        <nav className="space-x-4 text-sm">
          <Link to="/" className={loc.pathname === '/' ? 'text-white' : 'text-gray-400 hover:text-white'}>Home</Link>
        </nav>
      </header>
      <main className="p-6">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
