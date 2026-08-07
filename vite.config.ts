import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Browser development keeps the two production channels distinct: /server-api
// is durable business state, while /api is the local execution compatibility
// adapter that will disappear with the legacy business backend.
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
      '/server-api': {
        target: 'http://localhost:8100',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/server-api/, '/api'),
      },
    },
  },
})
