import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // 127.0.0.1 statt localhost: uvicorn lauscht nur auf IPv4, "localhost" kostet unter Windows je neuer Verbindung ~0,2 s (IPv6-Fallback)
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
})
