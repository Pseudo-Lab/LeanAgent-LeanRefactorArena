import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({ plugins: [react()],
  cacheDir: process.env.PROJECT_CACHE_DIR ? `${process.env.PROJECT_CACHE_DIR}/dashboard/vite` : 'node_modules/.vite',
  server: { port: 4173, strictPort: true } });
