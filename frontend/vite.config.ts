import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'
// The UI calls /api on its own origin; in development Vite forwards it to the backend.
export default defineConfig({ plugins: [react()], server: { host: '127.0.0.1', port: 5173, proxy: { '/api': backend } } })
