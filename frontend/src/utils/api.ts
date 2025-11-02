import type { BuildRequest } from '@shared/types/build_types'

const BASE = (import.meta.env.VITE_BACKEND_URL as string) || `http://127.0.0.1:${import.meta.env.VITE_BACKEND_PORT || 45555}`
declare global { interface Window { forgex?: any } }

export async function startBuild(req: BuildRequest) {
  if (window.forgex?.startBuild) return window.forgex.startBuild(req)
  const res = await fetch(`${BASE}/start-build`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req) })
  return res.json()
}

export async function cancelBuild(build_id: string) {
  if (window.forgex?.cancelBuild) return window.forgex.cancelBuild(build_id)
  const res = await fetch(`${BASE}/cancel-build`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ build_id }) })
  return res.json()
}

export async function getBuildStatus(build_id: string) {
  if (window.forgex?.status) return window.forgex.status(build_id)
  const res = await fetch(`${BASE}/build-status/${build_id}`)
  return res.json()
}

export async function getBuildHistory() {
  const res = await fetch(`${BASE}/build-history`)
  return res.json()
}

export async function clearHistory() {
  const res = await fetch(`${BASE}/clear-history`, { method: 'POST' })
  return res.json()
}

export async function uploadProject(form: FormData) {
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
  return res.json()
}
