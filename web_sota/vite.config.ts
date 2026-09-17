import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    server: {
        host: '127.0.0.1',
        port: 10903,
        proxy: {
            '/api': { target: 'http://127.0.0.1:10904', changeOrigin: true },
        },
    },
});
