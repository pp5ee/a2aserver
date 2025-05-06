const { defineConfig } = require('@vue/cli-service')

// 检查是否在Vercel环境中
const isVercel = process.env.VERCEL === 'true'

module.exports = defineConfig({
  transpileDependencies: true,
  lintOnSave: false,
  // 添加开发服务器代理配置，解决CORS问题
  devServer: {
    port: 3001,
    // 允许任何主机头访问，解决"Invalid Host header"问题
    allowedHosts: 'all',
    // 设置为true，进一步解决主机头问题
    disableHostCheck: true,
    historyApiFallback: true,
    // 设置信任代理来自的标头
    headers: {
      'Access-Control-Allow-Origin': '*',
    },
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
  },
  // 使用相对路径，这在Vercel部署中很重要
  publicPath: '/',
  // 构建配置
  configureWebpack: {
    // 添加环境变量注入
    plugins: [],
    // 设置webpack开发服务器选项
    devServer: {
      disableHostCheck: true,
      public: 'agenticdao.net'
    }
  }
}) 