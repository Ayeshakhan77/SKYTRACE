import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // The backend's CORS allowlist is http://localhost:3000 and http://127.0.0.1:3000.
  server: { port: 3000, strictPort: true },
  preview: { port: 3000, strictPort: true },
})
