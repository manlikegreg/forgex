import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'

export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  server: {
    host: true, // bind to 0.0.0.0 for LAN/hosting
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
  },
})
