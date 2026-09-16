import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 前端走 /v1/* → wrapper (9001)
      '/v1': {
        target: 'http://127.0.0.1:9001',
        changeOrigin: true,
      },
      // 兼容旧路径（如果还有别的组件用 /api）
      '/api': {
        target: 'http://127.0.0.1:9001',
        changeOrigin: true,
      },
    },
  },
})
