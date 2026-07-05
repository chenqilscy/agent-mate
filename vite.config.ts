import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Local-first: the frontend (browser at :5173) talks to the local backend (:8000).
// We proxy /api so the browser sees a same-origin URL and SSE streams flow through untouched.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // Do not buffer — SSE needs to flush per event.
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache'
          })
        },
      },
    },
  },
})
