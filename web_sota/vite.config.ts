import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    server: {
        host: '127.0.0.1',
        port: 11204,
        proxy: {
            '/api': { target: 'http://127.0.0.1:11205', changeOrigin: true },
        },
    },
});
