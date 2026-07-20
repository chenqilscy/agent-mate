import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Local-first: the frontend (browser at :8102) talks to the local backend (:8101).
// We proxy /api so the browser sees a same-origin URL and SSE streams flow through untouched.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 8102,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8101',
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
