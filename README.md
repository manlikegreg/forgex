# ForgeX — Universal Project Bundler

ForgeX is a desktop app (Electron) with a React + Vite + TypeScript frontend and a FastAPI backend. It detects project types, lets you configure build options, runs builds in a sandbox, streams logs in real-time, and stores build history in SQLite.

Main features
- Import folder or zip
- Auto-detect language (Python, Node, Java, Go, Batch, Rust, C#)
- Edit start command and advanced options
- Choose output formats (.exe/.msi/.app/.AppImage/.deb/.zip)
- Python end-to-end build via PyInstaller with venv
- Real-time log streaming via WebSocket
- Build history in SQLite at ~/.forgex/forgex.db
- Electron-packaged app via electron-builder

Prereqs
- Node.js 18+
- Python 3.11+
- For packaging: electron-builder (installed via frontend devDependencies), platform toolchains (NSIS for Windows, etc.)

Quick start (dev)
1. Backend: pip install -r backend/requirements.txt
2. Frontend: cd frontend && npm install
3. Start everything (dev with Electron):
   - bash: ./scripts/dev.sh
   - or manually:
     - python -m uvicorn backend.main:app --host 127.0.0.1 --port 45555
     - cd frontend && npm run dev:electron

Build the desktop app
- ./scripts/build-all.sh
  - Builds frontend and then runs electron-builder using electron/electron-builder.yml
  - Artifacts are placed in build/

Demonstration (Python Flask)
- Import a Flask project containing app.py
- Configure uses suggested command python app.py
- Start build -> venv + pip install + pyinstaller --onefile -> artifact appears under build/<project>/<build_id>/

Security & Sandboxing
- Builds run in a temp workspace ~/.forgex/tmp
- Python builds use a venv (.venv) for dependency isolation
- Command whitelist and blacklist enforced in backend/api/utils/security.py
- Per-build timeout default 20 minutes (FORGEX_BUILD_TIMEOUT)

API
- FastAPI endpoints in backend/api/routes.py per spec
- WebSocket: ws://localhost:45555/ws/builds; send {"type":"subscribe","build_id":"..."}

Electron IPC
- Channels: forgex:import, forgex:start-build, forgex:cancel-build, forgex:status

Testing & CI
- Run pytest in backend (example test included):
  - pip install pytest
  - pytest
- GitHub Actions workflow skeleton is in .github/workflows/ci.yml

Notes
- Node/Java/Go/Batch adapters are stubs with TODOs and clear guidance
- TailwindCSS is configured via global.css; add tailwind/postcss configs if you customize
- For installers (.msi/.dmg/.deb), ensure platform prerequisites are installed

Deployment
- See DEPLOYMENT.md for Render (backend) and Netlify (frontend) setup with commands and env vars

## Platform-specific setup and usage

The following instructions cover Windows, macOS, and Linux for development, packaging, and optional Windows code signing.

### Common prerequisites (all platforms)
- Node.js 18+
- Python 3.11+
- Git (for cloning and optional GitHub actions)

Dev quick start (all platforms):
- Backend: `pip install -r backend/requirements.txt`
- Frontend: `cd frontend && npm install`
- Run both (dev): `python dev.py`
  - Frontend served by Vite; Backend on FastAPI (see console for ports)

### Windows
Prereqs
- Node.js 18+
- Python 3.11+
- (Optional, for code signing) Windows 10/11 SDK (for `signtool.exe`)
  - Typically installed via Visual Studio Installer or Standalone Windows SDK

Dev
- Open PowerShell in the repo root and run:
  - `pip install -r backend/requirements.txt`
  - `cd frontend && npm install`
  - `python ..\dev.py` (or from root: `python dev.py`)

Packaging desktop app (Electron)
- Run: `scripts/build-all.sh` (use Git Bash or WSL) to build frontend then run electron-builder.
- Artifacts are created in `build/`.

Python EXE builds (via ForgeX UI)
- Upload/select your project, choose Language=Python and Output=.exe.
- Start command examples: `python app.py`, `uvicorn main:app --host 0.0.0.0 --port 8000`.
- Optional: Include `.env`, pause-on-exit, icon conversion to .ico, Windows autostart.

Windows code signing (optional)
- Requirements: `.pfx` code signing certificate and password; Windows SDK (signtool).
- In the ForgeX UI (Home page → Configuration):
  - Enable “Code sign (Windows)”
  - Set Certificate (.pfx) path and Password
  - Optionally set Timestamp URL (default `http://timestamp.digicert.com`) and Publisher URL (shown on signature)
- ForgeX uses `signtool` to sign the built `.exe` in the PyInstaller `dist/` folder before collecting artifacts.
- Secrets are not logged. Password is passed via an environment variable internally.

Verbose logs (per-build)
- Backend logs default to INFO level to reduce noise.
- To include DEBUG logs from the backend build process, enable the “Verbose logs” checkbox in the UI before starting a build.

### macOS
Prereqs
- `brew install node@18 python@3.11`
- Xcode Command Line Tools (for native tooling used by electron-builder)

Dev
- Same as common dev quick start: `python dev.py`

Packaging desktop app (Electron)
- `scripts/build-all.sh` creates a `.dmg` via electron-builder (see `electron/electron-builder.yml`).
- Note: Python EXE code signing described above is Windows-only. macOS app signing/notarization is not configured here.

### Linux (Ubuntu/Debian-based)
Prereqs
- `sudo apt-get update && sudo apt-get install -y curl git python3.11 python3.11-venv build-essential`
- Node.js 18+ (use NodeSource or nvm)

Dev
- Same as common dev quick start: `python dev.py`

Packaging desktop app (Electron)
- `scripts/build-all.sh` produces AppImage and .deb per `electron/electron-builder.yml`.

Notes
- Python builds run in a sandbox under `~/.forgex/tmp` and are packaged via PyInstaller in onefile mode with an isolated venv.
- Real-time logs stream over WebSocket; the Build Progress page lets you filter by level.
- On Windows, optional autostart can be registered via Task Scheduler or Startup folder.
