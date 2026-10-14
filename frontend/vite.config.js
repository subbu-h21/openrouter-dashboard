import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the Vite server proxies API calls to the FastAPI backend.
export default defineConfig({
  plugins: [react()],
  // Single bundle (~600 kB, ~180 kB gzipped) served from the local machine; not worth splitting.
  build: { chunkSizeWarningLimit: 1000 },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8787',
    },
  },
})
