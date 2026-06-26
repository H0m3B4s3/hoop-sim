import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build straight into the FastAPI package so `hoopr-web` serves the built SPA,
// and proxy /api to the backend during `npm run dev`.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../hoopr/web/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
})
