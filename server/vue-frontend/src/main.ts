import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import api from './services/api'

// 在控制台输出启动信息
console.log('Vue应用启动中...')
console.log('API基础URL:', api.defaults.baseURL)
console.log('当前环境:', process.env.NODE_ENV)

const app = createApp(App)

// 全局配置
app.config.errorHandler = (err, vm, info) => {
  console.error('全局错误:', err, info)
}

// 全局属性
app.config.globalProperties.$api = api

// 使用插件
app.use(store)
app.use(router)

// 挂载应用
app.mount('#app') 