import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// React Flow injects styles at runtime, so inline styles have to stay allowed.
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000",
  "img-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ')

// The dev server needs 'unsafe-inline' scripts for HMR, so the policy is only
// applied to the built application.
function injectContentSecurityPolicy(): Plugin {
  return {
    name: 'inject-csp',
    apply: 'build',
    transformIndexHtml(html) {
      return {
        html,
        tags: [
          {
            tag: 'meta',
            attrs: { 'http-equiv': 'Content-Security-Policy', content: CONTENT_SECURITY_POLICY },
            injectTo: 'head-prepend',
          },
        ],
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), injectContentSecurityPolicy()],
  // Loopback only: the local API and web app are single-user tools.
  server: { host: '127.0.0.1', port: 6002, strictPort: true },
  preview: { host: '127.0.0.1', port: 6002, strictPort: true },
})
