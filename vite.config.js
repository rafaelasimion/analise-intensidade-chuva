import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Em desenvolvimento, /api vai para o FastAPI local (npm run dev:api).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: {
          graficos: ['echarts', 'zrender'],
          react: ['react', 'react-dom', 'react-router'],
        },
      },
    },
  },
});
