import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { inspectAttr } from 'kimi-plugin-inspect-react'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  // inspectAttr inyecta code-path="fichero:linea:columna" en cada elemento JSX.
  // Sin apply:'serve' tambien lo hace en el build, publicando el arbol de
  // fuentes en el DOM del dashboard.
  plugins: [{ ...inspectAttr(), apply: 'serve' }, react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8600',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8600',
        ws: true,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
