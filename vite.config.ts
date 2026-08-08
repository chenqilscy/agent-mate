import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Browser development keeps the two production channels distinct: /server-api
// is durable business state, while /api is the local execution compatibility
// adapter that will disappear with the legacy business backend.
export default defineConfig({
  plugins: [react()],
  server: {
    // Keep the device UI on the same deterministic loopback family as the
    // Server and Local Agent. Node may otherwise resolve localhost to ::1.
    host: '127.0.0.1',
    port: 8102,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8101',
        changeOrigin: true,
        // Do not buffer — SSE needs to flush per event.
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache'
          })
        },
      },
      '/server-api': {
        target: 'http://127.0.0.1:8100',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/server-api/, '/api'),
      },
    },
  },
})
