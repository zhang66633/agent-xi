import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  server: {
    port: 5180,
    proxy: {
      '/ws': {
        target: 'ws://127.0.0.1:9731',
        ws: true,
      },
      '/api': {
        target: 'http://127.0.0.1:9731',
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
