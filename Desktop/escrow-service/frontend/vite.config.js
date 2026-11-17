import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev (and `vite preview`) the browser talks to /api/... and Vite forwards it to the backend,
// so there are no CORS headaches. In production, nginx does the same job (see frontend/Caddyfile).
const target = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'
const proxy = { '/api': { target, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') } }

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test/setup.js'] },
})
