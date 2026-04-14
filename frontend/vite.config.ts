import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/upload': 'http://localhost:8000',
      '/chat': 'http://localhost:8000',
      '/reset': 'http://localhost:8000',
    },
  },
})
