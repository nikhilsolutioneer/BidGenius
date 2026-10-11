import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({
  plugins: [react({ jsxImportSource: '@bidgenius/i18n' }), tailwindcss(), {
    name: 'localization-runtime-single-instance',
    configResolved(config) {
      // React's plugin adds JSX runtimes to dependency prebundling. This runtime
      // is application code and must share the live language store with the UI.
      config.optimizeDeps.include = config.optimizeDeps.include?.filter(id => !id.startsWith('@bidgenius/i18n'));
    },
  }],
  resolve: { alias: { '@bidgenius/i18n': decodeURIComponent(new URL('./src/i18n', import.meta.url).pathname).replace(/^\/(\w:)/, '$1') } },
  optimizeDeps: { exclude: ['@bidgenius/i18n', '@bidgenius/i18n/jsx-runtime', '@bidgenius/i18n/jsx-dev-runtime'] },
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { chunkSizeWarningLimit: 700 },
});
