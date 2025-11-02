# Deployment Guide for ForgeX

This guide shows how to deploy the backend (FastAPI) to Render and the frontend (Vite React) to Netlify. The Electron desktop app is packaged locally and not deployed to these hosts.

Overview
- Backend: Render Web Service (FastAPI/uvicorn)
- Frontend: Netlify Static Site (Vite build)
- Configure frontend to call the hosted backend via env vars

Prerequisites
- A Render account
- A Netlify account
- This repository hosted on GitHub/GitLab/Bitbucket

1) Deploy Backend to Render
- In repo root, the included render.yaml defines two services (backend web service + optional static site). The backend entry:
  - Build: pip install -r backend/requirements.txt
  - Start: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
  - Env var FORGEX_BACKEND_PORT=$PORT (used by the app)

Steps (Render Dashboard)
1. New Blueprint -> Select this repo
2. Confirm the plan (Free is fine) and click Apply
3. Wait for deploy to finish; you’ll get a URL like https://forgex-backend.onrender.com

Manual (Render CLI alternative)
- Update render.yaml if needed
- Push to main; Render auto-deploys

2) Deploy Frontend to Netlify
- The included netlify.toml builds the frontend and publishes frontend/dist.
- Set env variables so the app calls your Render backend.

Steps (Netlify Dashboard)
1. New site from Git -> choose this repo
2. Build command: (auto from netlify.toml) cd frontend && npm ci && npm run build
3. Publish directory: (auto) frontend/dist
4. Environment variables (important):
   - VITE_BACKEND_URL = https://forgex-backend.onrender.com
   - VITE_BACKEND_WS = wss://forgex-backend.onrender.com
   - NODE_VERSION = 18
5. Deploy site

Local build preview
- Frontend only against a hosted backend:
  - cd frontend
  - set VITE_BACKEND_URL to your backend URL
  - npm run build && npx serve dist

3) CORS and WebSocket
- Backend has permissive CORS enabled. If you harden it, add your Netlify domain to allow_origins.
- WS endpoint is {VITE_BACKEND_WS}/ws/builds.

4) Commands Summary
Backend (Render)
- Build: pip install -r backend/requirements.txt
- Start: uvicorn backend.main:app --host 0.0.0.0 --port $PORT

Frontend (Netlify)
- Build: cd frontend && npm ci && npm run build
- Publish: frontend/dist

5) Electron Packaging (local)
- cd frontend && npm run build
- bash scripts/build-all.sh

Troubleshooting
- 404 on refresh (SPA): netlify.toml includes redirects to index.html
- Mixed content: ensure https URLs for VITE_BACKEND_URL and VITE_BACKEND_WS
- Logs not streaming: verify VITE_BACKEND_WS, check that Render service is healthy and allows websockets
