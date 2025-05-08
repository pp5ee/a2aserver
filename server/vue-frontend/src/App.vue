<template>
  <div id="app">
    <header class="app-header">
      <div class="logo">
        <img src="@/assets/logo.svg" alt="A2A Logo" />
        <h1>A2A 平台</h1>
      </div>
      
      <!-- 导航菜单 -->
      <nav class="main-nav">
        <router-link to="/">主页</router-link>
        <router-link to="/conversation">会话</router-link>
        <router-link to="/agents">代理</router-link>
        <router-link to="/solanaprogram">Solana程序</router-link>
        <router-link to="/settings">设置</router-link>
      </nav>
      
      <!-- API设置按钮（仅在Vercel环境显示） -->
      <button v-if="isVercelEnv" @click="showApiConfig" class="api-config-btn">
        <i class="fas fa-cog"></i> API配置
      </button>
      
      <!-- Phantom钱包组件 -->
      <div class="wallet-container">
        <phantom-wallet 
          @wallet-connected="onWalletConnected" 
          @wallet-disconnected="onWalletDisconnected"
        />
      </div>
    </header>
    
    <main class="app-content">
      <!-- 未连接钱包提示 (仅在主页显示) -->
      <div v-if="!walletConnected && $route.path === '/'" class="wallet-suggestion">
        <div class="info-box">
          <h2>推荐连接Solana钱包</h2>
          <p>连接钱包可以体验个性化的代理和会话管理功能。</p>
        </div>
      </div>
      
      <!-- 主要内容 - 始终显示路由视图 -->
      <router-view />
    </main>
    
    <!-- API URL配置组件 -->
    <api-url-config ref="apiConfigComponent" />
    
    <!-- 通知提示 -->
    <div v-if="notification" class="notification" :class="notification.type">
      <div class="notification-content">
        <i class="notification-icon" :class="getNotificationIcon()"></i>
        <span>{{ notification.message }}</span>
      </div>
      <button @click="clearNotification" class="close-btn">
        <i class="fas fa-times"></i>
      </button>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { apiService } from './services/api'
import PhantomWallet from './components/PhantomWallet.vue'
import ApiUrlConfig from './components/ApiUrlConfig.vue'

interface NotificationType {
  message: string;
  type: 'success' | 'error' | 'warning' | 'info';
}

export default defineComponent({
  name: 'App',
  components: {
    PhantomWallet,
    ApiUrlConfig
  },
  setup() {
    const route = useRoute()
    const apiConfigComponent = ref<any>(null)
    
    // Vercel环境检测
    const isVercelEnv = computed(() => {
      return typeof window !== 'undefined' && 
             (window.location.hostname.includes('vercel.app') || 
              window?.location?.hostname?.includes?.('localhost') && (window as any)._debugVercelEnv);
    })
    
    // API连接状态
    const apiError = ref(false)
    const apiErrorMessage = ref('')
    const apiErrorDetails = ref('')
    const isLoading = ref(false)
    
    // 钱包状态
    const walletConnected = ref(false)
    const walletAddress = ref('')
    const requireWallet = ref(true)
    const notification = ref<NotificationType | null>(null)
    
    // 检查API连接
    const checkApiConnection = async () => {
      try {
        isLoading.value = true
        await apiService.listAgents()
        apiError.value = false
      } catch (error: any) {
        apiError.value = true
        apiErrorMessage.value = '无法连接到后端服务器。请确保服务器正在运行。'
        if (error.message) {
          apiErrorDetails.value = error.message
        }
        console.error('API连接错误:', error)
      } finally {
        isLoading.value = false
      }
    }
    
    // 重试连接
    const retryConnection = () => {
      checkApiConnection()
    }
    
    // 检查钱包连接
    const checkWalletConnection = async () => {
      const result = await apiService.checkWalletConnection()
      walletConnected.value = result.connected
      walletAddress.value = result.address || ''
      
      if (result.connected) {
        console.log('已检测到钱包连接:', walletAddress.value)
      }
    }
    
    // 钱包连接处理
    const onWalletConnected = (address: string) => {
      walletConnected.value = true
      walletAddress.value = address
      showNotification('钱包已连接', 'success')
      
      // 加载用户数据
      fetchUserData()
    }
    
    // 钱包断开处理
    const onWalletDisconnected = () => {
      walletConnected.value = false
      walletAddress.value = ''
      showNotification('钱包已断开连接', 'info')
    }
    
    // 加载用户数据
    const fetchUserData = async () => {
      try {
        // 获取代理列表
        const agentsResponse = await apiService.listAgents()
        console.log('获取到用户代理:', agentsResponse.data.result)
        
        // 获取会话列表
        const conversationsResponse = await apiService.listConversations()
        console.log('获取到用户会话:', conversationsResponse.data.result)
      } catch (error) {
        console.error('获取用户数据失败:', error)
      }
    }
    
    // 显示通知
    const showNotification = (message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info') => {
      notification.value = { message, type }
      
      // 5秒后自动关闭
      setTimeout(() => {
        if (notification.value && notification.value.message === message) {
          clearNotification()
        }
      }, 5000)
    }
    
    // 清除通知
    const clearNotification = () => {
      notification.value = null
    }
    
    // 获取通知图标类名
    const getNotificationIcon = () => {
      const iconMap = {
        success: 'fas fa-check-circle',
        error: 'fas fa-exclamation-circle',
        warning: 'fas fa-exclamation-triangle',
        info: 'fas fa-info-circle'
      }
      
      return iconMap[notification.value?.type || 'info']
    }
    
    // 显示API配置
    const showApiConfig = () => {
      if (apiConfigComponent.value) {
        apiConfigComponent.value.showConfigPanel();
      }
    }
    
    // 组件挂载
    onMounted(() => {
      // 检查API连接
      checkApiConnection()
      
      // 检查钱包连接
      checkWalletConnection()
      
      // 监听钱包错误事件
      window.addEventListener('wallet-error', handleWalletError as EventListener)
      
      // 监听签名错误事件
      window.addEventListener('signature-error', handleSignatureError as EventListener)
    })
    
    // 组件卸载
    onUnmounted(() => {
      // 移除事件监听器
      window.removeEventListener('wallet-error', handleWalletError as EventListener)
      window.removeEventListener('signature-error', handleSignatureError as EventListener)
    })
    
    // 处理钱包错误
    const handleWalletError = (event: CustomEvent) => {
      showNotification(event.detail.message, 'error')
    }
    
    // 处理签名错误
    const handleSignatureError = (event: CustomEvent) => {
      showNotification(event.detail.message, 'error')
    }
    
    return {
      // 路由状态
      isAuthPage: route.path === '/auth',
      
      // API状态
      apiError,
      apiErrorMessage,
      apiErrorDetails,
      isLoading,
      retryConnection,
      
      // 钱包状态
      walletConnected,
      walletAddress,
      requireWallet,
      onWalletConnected,
      onWalletDisconnected,
      
      // 通知
      notification,
      clearNotification,
      getNotificationIcon,
      
      // Vercel环境检测
      isVercelEnv,
      showApiConfig,
      apiConfigComponent
    }
  }
})
</script>

<style>
#app {
  font-family: 'Google Sans', Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #2c3e50;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

body {
  margin: 0;
  padding: 0;
}

/* 导航样式 */
.main-nav {
  display: flex;
  align-items: center;
  margin: 0 2rem;
}

.main-nav a {
  color: #333;
  text-decoration: none;
  padding: 0.5rem 1rem;
  margin: 0 0.5rem;
  border-radius: 4px;
  transition: all 0.3s ease;
}

.main-nav a:hover {
  background-color: rgba(78, 68, 206, 0.1);
}

.main-nav a.router-link-active,
.main-nav a.router-link-exact-active {
  color: #4e44ce;
  font-weight: 500;
  background-color: rgba(78, 68, 206, 0.1);
}

nav {
  padding: 15px;
  background-color: #f5f5f5;
  border-bottom: 1px solid #e0e0e0;
}

nav a {
  font-weight: bold;
  color: #2c3e50;
  padding: 0 10px;
  text-decoration: none;
}

nav a.router-link-exact-active {
  color: #42b983;
}

.api-error {
  max-width: 600px;
  margin: 100px auto;
  padding: 20px;
  background-color: #fff3f3;
  border: 1px solid #ffcfcf;
  border-radius: 4px;
  text-align: center;
}

.api-error h2 {
  color: #e53935;
  margin-top: 0;
}

.error-details {
  margin: 15px 0;
  text-align: left;
  background-color: #f8f8f8;
  padding: 10px;
  border-radius: 4px;
  overflow-x: auto;
}

.error-details pre {
  margin: 0;
  font-size: 12px;
  white-space: pre-wrap;
}

.api-error button {
  padding: 10px 20px;
  background-color: #42b983;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
  margin-top: 15px;
}

.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.8);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.loading-spinner {
  width: 50px;
  height: 50px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #42b983;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.loading-text {
  margin-top: 15px;
  font-size: 18px;
  color: #2c3e50;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* 全局样式 */
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: 'Google Sans', Arial, sans-serif;
  background-color: #f5f5f5;
  color: #333;
  line-height: 1.6;
}

/* 头部样式 */
.app-header {
  background-color: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 1rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.logo {
  display: flex;
  align-items: center;
}

.logo img {
  height: 40px;
  margin-right: 1rem;
}

.logo h1 {
  font-size: 1.5rem;
  font-weight: 500;
  color: #333;
}

.wallet-container {
  width: 300px;
}

/* 主要内容区域 */
.app-content {
  flex: 1;
  padding: 2rem;
}

/* 钱包提示 */
.wallet-suggestion {
  margin-bottom: 2rem;
  display: flex;
  justify-content: center;
}

.info-box {
  background-color: #fff;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  max-width: 500px;
}

.info-box h2 {
  margin-bottom: 1rem;
  color: #333;
}

.info-box p {
  color: #666;
}

/* 通知提示 */
.notification {
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  min-width: 300px;
  padding: 1rem;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 1000;
}

.notification-content {
  display: flex;
  align-items: center;
}

.notification-icon {
  margin-right: 0.75rem;
  font-size: 1.25rem;
}

.notification.success {
  background-color: #e8f5e9;
  color: #2e7d32;
  border-left: 4px solid #2e7d32;
}

.notification.error {
  background-color: #ffebee;
  color: #c62828;
  border-left: 4px solid #c62828;
}

.notification.warning {
  background-color: #fff8e1;
  color: #f57f17;
  border-left: 4px solid #f57f17;
}

.notification.info {
  background-color: #e3f2fd;
  color: #1565c0;
  border-left: 4px solid #1565c0;
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.close-btn:hover {
  opacity: 1;
}

.api-config-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 12px;
  background-color: #4a5568;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  margin-right: 10px;
  transition: background-color 0.2s;
}

.api-config-btn:hover {
  background-color: #2d3748;
}

.api-config-btn i {
  font-size: 16px;
}
</style> 