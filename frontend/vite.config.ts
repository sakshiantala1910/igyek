import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the API runs in its own container on :8000; the proxy keeps
// the frontend origin-relative so the same fetch code works in production,
// where Vercel routes /api/* to the Python function.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5199,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: { outDir: 'dist', sourcemap: true },
})
