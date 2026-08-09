/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  base: '/etf-radar/',
  plugins: [react()],
  publicDir: path.resolve(__dirname, '../data'),
  build: { outDir: 'dist' },
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
    exclude: ['node_modules', 'dist', 'e2e/**'],
    coverage: {
      provider: 'v8',
      reporter: ['lcov', 'text'],
      reportsDirectory: 'coverage',
      reportOnFailure: true,
      exclude: [
        'node_modules/**', 'dist/**', '**/*.d.ts', 'coverage/**',
        'vite.config.ts', 'src/test-setup.ts', 'src/__fixtures__/**', 'src/__tests__/**',
      ],
    },
  },
});
