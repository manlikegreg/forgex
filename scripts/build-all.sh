set -euo pipefail

# Build frontend
( cd frontend && npm install && npm run build )

# Package Electron app using config
( cd frontend && npx electron-builder -c ../electron/electron-builder.yml )
