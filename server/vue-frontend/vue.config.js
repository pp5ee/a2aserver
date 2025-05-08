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
    // 适配新版本webpack-dev-server
    // 注意：disableHostCheck已被废弃，使用allowedHosts代替
    historyApiFallback: true,
    // 设置信任代理来自的标头
    headers: {
      'Access-Control-Allow-Origin': '*',
    },
    // 客户端配置
    client: {
      webSocketURL: 'auto://0.0.0.0:0/ws',
      overlay: {
        errors: true,
        warnings: false,
      },
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
      },
      '/api/metadata-proxy': {
        target: 'http://8.214.38.69:10003',
        changeOrigin: true,
        pathRewrite: {
          '^/api/metadata-proxy': ''
        },
        logLevel: 'debug'
      }
    }
  },
  // 使用相对路径，这在Vercel部署中很重要
  publicPath: '/',
  // 构建配置
  configureWebpack: {
    resolve: {
      fallback: {
        "assert": require.resolve("assert/"),
        "stream": require.resolve("stream-browserify"),
        "buffer": require.resolve("buffer/"),
        "crypto": require.resolve("crypto-browserify"),
        "path": require.resolve("path-browserify"),
        "fs": false,
        "os": require.resolve("os-browserify/browser"),
      }
    },
    plugins: [
      // 添加Buffer polyfill
      new (require('webpack')).ProvidePlugin({
        Buffer: ['buffer', 'Buffer'],
        process: 'process/browser',
      }),
    ]
  }
}) 