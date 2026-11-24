import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { NOME_CURTO, SITE } from './src/config.js';

// O nome do site vem de src/config.js (também no index.html: %NOME_SITE%, %DESCRICAO_SITE%)
const nomeDoSite = {
  name: 'nome-do-site',
  transformIndexHtml: (html) =>
    html.replaceAll('%NOME_SITE%', NOME_CURTO).replaceAll('%DESCRICAO_SITE%', SITE.descricao),
};

// Em desenvolvimento, /api vai para o FastAPI local (npm run dev:api).
export default defineConfig({
  plugins: [react(), nomeDoSite],
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
