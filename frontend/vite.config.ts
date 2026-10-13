import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';

function readDevProxyToken(): string | null {
  const tokenFile = process.env.ORDIVANT_DEV_PROXY_TOKEN_FILE;
  const token = tokenFile
    ? readFileSync(tokenFile, 'utf8').trim()
    : process.env.ORDIVANT_DEV_PROXY_TOKEN?.trim() ?? '';
  if ((tokenFile || process.env.ORDIVANT_DEV_PROXY_TOKEN) && !token) {
    throw new Error('The configured Ordivant development proxy token is empty.');
  }
  return token || null;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const devProxyToken = readDevProxyToken();
  const injectDevProxyToken = (proxy: import('vite').HttpProxy.Server) => {
    if (devProxyToken) {
      proxy.on('proxyReq', (proxyRequest) => {
        proxyRequest.setHeader('X-Ordivant-Dev-Proxy', devProxyToken);
      });
    }
  };
  const watchInterval = Number(env.VITE_WATCH_INTERVAL) || 1000;
  return {
    plugins: [react()],
    server: {
      host: env.VITE_HOST || '127.0.0.1',
      port: 5173,
      strictPort: true,
      watch: env.VITE_WATCH_USEPOLLING === 'true'
        ? { usePolling: true, interval: watchInterval }
        : undefined,
      proxy: {
        '/auth-api': {
          target: env.VITE_IDENTITY_API_TARGET || 'http://127.0.0.1:8030',
          changeOrigin: false,
          rewrite: (path) => path.replace(/^\/auth-api/, '/api/auth'),
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyRequest, request) => {
              // The trusted proxy supplies the socket peer, never a browser header.
              const address = request.socket.remoteAddress;
              if (address) proxyRequest.setHeader('X-Real-IP', address);
              else proxyRequest.removeHeader('X-Real-IP');
            });
          },
        },
        '/knowledge-api': {
          target: env.VITE_KNOWLEDGE_API_TARGET || 'http://127.0.0.1:8010',
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/knowledge-api/, '/api'),
          configure: injectDevProxyToken,
        },
        '/code-api': {
          target: env.VITE_CODE_API_TARGET || 'http://127.0.0.1:8020',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/code-api/, '/api'),
          configure: injectDevProxyToken,
        },
        '/api': {
          target: env.VITE_API_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          ws: true,
          configure: injectDevProxyToken,
        },
      },
    },
  };
});
