import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Ports 8000/5173 are taken by other projects on this machine, hence 8010/5183.
// Override the backend port with BACKEND_PORT when starting vite.
const BACKEND_PORT = process.env.BACKEND_PORT ?? '8010'
const DEV_PORT = Number(process.env.FRONTEND_PORT ?? 5183)

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: DEV_PORT,
    // Fail loudly instead of silently drifting to another port, so the
    // CORS origin configured in the backend keeps matching.
    strictPort: true,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${BACKEND_PORT}`,
        changeOrigin: true,
        // SSE over this proxy: make sure nothing buffers the stream, otherwise
        // /api/analyze/stream would arrive in one lump at the end.
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache, no-transform'
              delete proxyRes.headers['content-encoding']
            }
          })
        },
      },
    },
  },
})
