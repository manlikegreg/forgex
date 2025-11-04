# ForgeX Codebase Overview

## Project Description
**ForgeX** is a universal project bundler desktop application that packages Python projects into standalone executables. It features an Electron frontend with React + Vite + TypeScript and a FastAPI backend.

### Key Features
- Upload folder/zip projects
- Automatic language detection (Python, Node.js, Go, Rust, Java, C#)
- Configure working directory + start command
- Build Python apps to single EXE using PyInstaller
- Real-time build logs via WebSocket
- Download build artifacts
- Optional Windows code signing
- Optional environment variable inclusion in builds

---

## Architecture Overview

### Technology Stack
- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS + Framer Motion
- **Backend**: FastAPI + Python 3.11+
- **Desktop**: Electron 30
- **Package Management**: npm + pip
- **Build Tool**: PyInstaller (for Python EXE generation), electron-builder (for app packaging)

### Directory Structure
```
forgex/
├── backend/                    # FastAPI backend
│   ├── main.py                # FastAPI app entry, WebSocket, middleware setup
│   ├── api/
│   │   ├── routes.py          # HTTP endpoints (upload, build, status, download)
│   │   ├── build_runner.py    # Build orchestration and execution
│   │   ├── compiler_engine.py # Language detection & project inspection
│   │   ├── models/            # Pydantic models (BuildRequest, etc.)
│   │   └── utils/             # File system utilities
│   └── services/
│       ├── db.py              # SQLite database interface
│       ├── logger.py          # Log streaming and WebSocket management
│       └── presets.py         # Configuration presets
├── frontend/                   # React + Vite frontend
│   ├── src/
│   │   ├── App.tsx            # Root component with outlet
│   │   ├── main.tsx           # React-Router setup
│   │   ├── pages/
│   │   │   ├── Home.tsx       # Project upload & configuration
│   │   │   ├── Configure.tsx  # Build settings editor
│   │   │   ├── BuildProgress.tsx  # Live build logs (WebSocket)
│   │   │   └── Result.tsx     # Download artifacts
│   │   ├── components/
│   │   │   ├── FilePicker.tsx
│   │   │   ├── LanguageCard.tsx
│   │   │   ├── OutputSelector.tsx
│   │   │   ├── StartCommandEditor.tsx
│   │   │   ├── BuildLogViewer.tsx
│   │   │   └── ErrorBoundary.tsx
│   │   ├── hooks/
│   │   │   └── useBuild.ts    # Custom hook for build state management
│   │   └── utils/
│   │       └── api.ts         # API client (HTTP + WebSocket)
│   ├── package.json           # npm scripts & dependencies
│   ├── vite.config.ts         # Vite configuration
│   └── tsconfig.json
├── electron/                  # Electron app wrapper
│   ├── main.js                # Electron main process
│   └── preload.js             # Preload script for IPC
├── shared/                    # Shared types & constants
│   ├── constants/
│   │   └── languages.ts       # Language definitions
│   └── types/
│       └── build_types.ts     # TypeScript types (shared)
├── scripts/                   # Build & development scripts
│   ├── build-all.sh           # Frontend + electron-builder
│   └── dev.py                 # Dev orchestrator
├── test/                      # Test utilities
├── dev.py                     # Development server orchestrator
├── netlify.toml               # Netlify configuration (frontend deployment)
├── render.yaml                # Render deployment config
└── README.md                  # Setup & usage guide

```

---

## Core Components

### Backend (`backend/`)

#### **main.py** - FastAPI Application
- Initializes FastAPI app with CORS middleware
- WebSocket endpoint at `/ws/builds` for real-time log streaming
- HTTP request logging middleware (configurable verbosity)
- Routes include: upload, build, status, download, history
- Environment-based configuration (log level, host, port)

#### **api/routes.py** - HTTP Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/upload` | POST | Accept zip or file list; stage to temp project folder |
| `/start-build` | POST | Queue a new build with BuildRequest |
| `/cancel-build` | POST | Cancel an in-progress build |
| `/build-status/{build_id}` | GET | Get build status, output files, metadata |
| `/build-history` | GET | List recent builds (paginated) |
| `/clear-history` | POST | Wipe DB and log files |
| `/download/{build_id}/{filename}` | GET | Download artifact |

#### **api/compiler_engine.py** - Language Detection & Inspection
- `detect_language(project_path)` → Analyzes file markers (package.json, requirements.txt, go.mod, etc.) to determine language with confidence scores
- `find_python_entries(project_path)` → Finds candidate Python entry points (app.py, main.py, etc.) with heuristic scoring
- `suggest_command(language, project_path)` → Returns recommended start command
- `inspect_project(project_path)` → Returns full analysis (language, scores, entry candidates, suggested command)

#### **api/build_runner.py** - Build Orchestration
- Manages build queue and execution
- Handles PyInstaller invocation for Python builds
- Streams logs to WebSocket subscribers
- Manages build artifacts and output

#### **services/db.py** - Database
- SQLite database for build history
- Stores build metadata: build_id, status, timestamps, output files, errors, configuration

#### **services/logger.py** - Log Management
- Manages log files per build
- WebSocket subscription system for real-time log streaming
- Handles publish/subscribe pattern for build logs

### Frontend (`frontend/src/`)

#### **main.tsx** - React Router Setup
- Root routing with BrowserRouter
- Routes:
  - `/` → Home (upload & config)
  - `/progress/:buildId` → BuildProgress (live logs)
  - `/result/:buildId` → Result (artifacts download)

#### **pages/Home.tsx**
- File picker for upload
- Project inspection / language detection
- Build configuration UI

#### **pages/BuildProgress.tsx**
- WebSocket connection to `/ws/builds` for real-time logs
- Log level filtering (DEBUG, INFO, WARN, ERROR)
- Cancel build button

#### **pages/Result.tsx**
- Display completed build status
- List and download artifacts

#### **utils/api.ts** - API Client
- HTTP client for REST endpoints (upload, status, history, download)
- WebSocket client for log streaming

#### **hooks/useBuild.ts**
- Custom React hook managing build state
- Integrates with API client

#### **components/**
- **FilePicker.tsx** - Drag-and-drop file upload
- **LanguageCard.tsx** - Display detected language with confidence
- **OutputSelector.tsx** - Choose output type (EXE, etc.)
- **StartCommandEditor.tsx** - Edit start command
- **BuildLogViewer.tsx** - Display and filter logs
- **ErrorBoundary.tsx** - Error handling wrapper

### Electron (`electron/`)
- **main.js** - Electron main process; loads frontend from Vite dev server or built assets
- **preload.js** - Preload script for secure IPC (if needed)

### Shared (`shared/`)
- **types/build_types.ts** - Shared TypeScript types
- **constants/languages.ts** - Language definitions and metadata

---

## Development Workflow

### Quick Start
1. **Install dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   cd frontend && npm install
   ```

2. **Run dev servers**:
   ```bash
   python dev.py
   ```
   - Backend: FastAPI on `127.0.0.1:45555`
   - Frontend: Vite dev server on `http://127.0.0.1:5173`

### Build Desktop App
```bash
./scripts/build-all.sh
```
- Builds React frontend with Vite
- Packages with electron-builder
- Artifacts in `build/` directory

### Environment Variables (Backend)
- `FORGEX_BACKEND_PORT` - Server port (default: 45555)
- `FORGEX_BACKEND_HOST` - Server host (default: 127.0.0.1)
- `FORGEX_LOG_LEVEL` - Log level (default: INFO)
- `FORGEX_ACCESS_LOG` - Enable access logs (default: disabled)
- `FORGEX_HTTP_LOG` - HTTP log verbosity (default: minimal)

---

## Build Process Flow

1. **User uploads project** → `/upload` endpoint stores files in `~/.forgex/uploads/`
2. **User configures build** → Sets language, working directory, start command
3. **User starts build** → `/start-build` queues BuildRequest
4. **Build runner executes**:
   - Create isolated venv
   - Install dependencies (pip, npm)
   - Run PyInstaller (for Python) or appropriate compiler
   - Collect artifacts
5. **Logs stream** → Backend publishes to WebSocket subscribers
6. **Build completes** → Results stored in DB, artifacts available for download

---

## Key Design Patterns

### Language Detection
- **Deterministic markers** (package.json, requirements.txt, go.mod, etc.) scored at 0.7–0.9
- **File-based heuristics** (*.py, *.go, *.rs files) scored at 0.02–0.05
- **Best match** selected via max confidence score

### Log Streaming
- **Real-time WebSocket** `/ws/builds` for live build logs
- **Publish-subscribe pattern** in `logger.py`
- **Client-side filtering** by log level

### Build State Management
- **Centralized DB** (SQLite) for build history
- **Async/await** for non-blocking operations
- **Build queue** managed by `build_runner.py`

---

## Deployment

### Netlify (Frontend)
- **Config**: `netlify.toml`
- **Build**: `cd frontend && npm ci && npm run build`
- **Publish**: `frontend/dist`
- **Environment**:
  - `VITE_BACKEND_URL` = Production API endpoint
  - `VITE_BACKEND_WS` = Production WebSocket endpoint

### Render (Backend)
- **Config**: `render.yaml`
- **Entrypoint**: Python FastAPI with uvicorn
- **Environment**: Database, log storage in `~/.forgex/`

---

## Important Notes

- **Python builds** execute in sandbox under `~/.forgex/tmp/`
- **PyInstaller** runs in onefile mode with isolated venv
- **Windows code signing** optional (requires .pfx certificate + signtool)
- **Vertical scaling** only; single-threaded build queue
- **File uploads** streamed to disk to minimize memory usage
- **CORS enabled** for local dev and Electron

