import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base: './' — сборка открывается из любой папки и из file://
// proxy: в dev можно задать VITE_API_URL= (пусто) и ходить на backend через Vite без CORS
export default defineConfig({
  plugins: [react()],
  base: './',
  server: { proxy: { '/api': process.env.API_PROXY ?? 'http://localhost:8080' } },
});
