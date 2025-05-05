const { defineConfig } = require('@vue/cli-service')
module.exports = defineConfig({
  transpileDependencies: true,
  lintOnSave: false,
  // 添加开发服务器代理配置，解决CORS问题
  devServer: {
    port: 8081,
    proxy: {
      '/api': {
        target: 'http://localhost:12000',
        changeOrigin: true,
        pathRewrite: {
          '^/api': ''
        },
        // 解决HTTPS问题（如果需要）
        secure: false,
        // 允许配置代理回调函数
        onProxyReq: (proxyReq, req, res) => {
          console.log('正向代理请求:', req.method, req.url);
        },
        onProxyRes: (proxyRes, req, res) => {
          console.log('代理响应状态码:', proxyRes.statusCode);
        }
      }
    }
  }
}) 