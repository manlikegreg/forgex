# ForgeX — Universal Project Bundler

Pinned — How to run your app (Working directory + Start command)
- Working directory controls where the command runs inside your uploaded project.
- If your entry is in a subfolder (e.g., test/main.py):
  - Working directory = . and Start command = uvicorn test.main:app --host 127.0.0.1 --port 8000
  - OR Working directory = test and Start command = uvicorn main:app --host 127.0.0.1 --port 8000
- For a single script: Start command = python path/to/script.py
- Use 127.0.0.1 or 0.0.0.0 as host (127.0.0 is invalid).

Quick usage
1) Backend: pip install -r backend/requirements.txt
2) Frontend: cd frontend && npm install
3) Dev: python dev.py (opens backend + frontend)
4) In the UI: Upload your project → set Working directory + Start command → Start build → download EXE.

ForgeX is a desktop app (Electron) with a React + Vite + TypeScript frontend and a FastAPI backend.

Minimal features
- Upload folder/zip
- Set Working directory + Start command (see pinned section)
- Build Python apps to a single EXE (PyInstaller)
- View live logs and download artifacts

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


Multiple processes
- Use a small launcher.py to start both processes, then set Start command = python launcher.py








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
