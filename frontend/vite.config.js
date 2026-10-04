import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base: './' — сборка открывается из любой папки и из file://
// proxy: в dev можно задать VITE_API_URL= (пусто) и ходить на backend через Vite без CORS
const apiProxy = {
  '/api': {
    target: 'http://backend:8080',
    changeOrigin: true,
    // rewrite: (path) => path.replace(/^\/api/, ''),
  },
};

export default defineConfig({
  plugins: [react()],
  base: '/',
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
});