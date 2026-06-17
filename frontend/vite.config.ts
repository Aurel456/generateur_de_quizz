import { fileURLToPath, URL } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import gzipPlugin from 'rollup-plugin-gzip';
import brotli from 'rollup-plugin-brotli';
import vue from '@vitejs/plugin-vue';

export default defineConfig(({ command, mode }) => {
    const envDir = './config';
    const env = loadEnv(mode, envDir, '');
    let server = {};

    if (command === 'serve') {
        server = {
            port: 8081,
            host: true,
            hmr: { overlay: true },
        };
    }

    return {
        envDir,
        server,
        preview: server,
        plugins: [
            vue(),
            brotli({ test: /\.(js|css|html|txt|json|svg)$/, minSize: 1000 }),
            gzipPlugin({ gzipOptions: { level: 9 }, minSize: 1000 }),
        ],
        base: `${env.VITE_APP_PUBLIC_PATH}/`,
        define: { global: 'window' },
        resolve: {
            alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
        },
    };
});
