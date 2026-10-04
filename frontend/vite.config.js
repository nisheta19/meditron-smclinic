import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Development proxy; the production image uses nginx.conf.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: './',
  server: { proxy: { '/api': loadEnv(mode, process.cwd(), '').API_PROXY || 'http://localhost:8080' } },
}));
