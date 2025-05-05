<template>
  <div v-if="showConfig" class="api-url-config">
    <div class="api-url-form">
      <h3>API配置</h3>
      <div class="form-group">
        <label for="apiUrl">API服务器地址</label>
        <input 
          type="text" 
          id="apiUrl" 
          v-model="apiUrl" 
          placeholder="请输入API服务器地址，例如：https://your-api-server.com"
          class="form-control"
        />
      </div>
      <div class="form-actions">
        <button @click="saveApiUrl" class="save-btn">保存</button>
        <button @click="hideConfig" class="cancel-btn">取消</button>
      </div>
      <div v-if="message" :class="['message', messageType]">
        {{ message }}
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted } from 'vue';
import { setApiBaseUrl } from '../config/env';

export default defineComponent({
  name: 'ApiUrlConfig',
  setup() {
    const apiUrl = ref('');
    const message = ref('');
    const messageType = ref('');
    const showConfig = ref(false);
    
    // 检查是否在Vercel环境中
    const isVercelEnv = computed(() => {
      return process.env.VERCEL === 'true' || 
             window.location.hostname.includes('vercel.app');
    });
    
    onMounted(() => {
      // 在Vercel环境中自动显示配置面板
      if (isVercelEnv.value) {
        showConfig.value = true;
        
        // 尝试从localStorage获取之前保存的API URL
        const savedApiUrl = localStorage.getItem('api_url');
        if (savedApiUrl) {
          apiUrl.value = savedApiUrl;
          setApiBaseUrl(savedApiUrl);
        }
      }
    });
    
    const saveApiUrl = () => {
      if (!apiUrl.value.trim()) {
        message.value = '请输入有效的API服务器地址';
        messageType.value = 'error';
        return;
      }
      
      try {
        // 检查URL格式是否有效
        new URL(apiUrl.value);
        
        // 保存到localStorage
        localStorage.setItem('api_url', apiUrl.value);
        
        // 设置API URL
        setApiBaseUrl(apiUrl.value);
        
        message.value = 'API服务器地址已保存';
        messageType.value = 'success';
        
        // 2秒后隐藏配置面板
        setTimeout(() => {
          showConfig.value = false;
        }, 2000);
      } catch (e) {
        message.value = '请输入有效的URL格式';
        messageType.value = 'error';
      }
    };
    
    const hideConfig = () => {
      showConfig.value = false;
    };
    
    // 公开一个方法，允许外部显示配置面板
    const showConfigPanel = () => {
      showConfig.value = true;
    };
    
    return {
      apiUrl,
      message,
      messageType,
      showConfig,
      saveApiUrl,
      hideConfig,
      showConfigPanel,
      isVercelEnv
    };
  }
});
</script>

<style scoped>
.api-url-config {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  z-index: 1000;
  display: flex;
  justify-content: center;
  align-items: center;
}

.api-url-form {
  background-color: white;
  padding: 20px;
  border-radius: 8px;
  width: 90%;
  max-width: 500px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

h3 {
  margin-top: 0;
  margin-bottom: 20px;
  color: #333;
}

.form-group {
  margin-bottom: 15px;
}

label {
  display: block;
  margin-bottom: 5px;
  color: #555;
}

.form-control {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

button {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.save-btn {
  background-color: #4CAF50;
  color: white;
}

.save-btn:hover {
  background-color: #45a049;
}

.cancel-btn {
  background-color: #f5f5f5;
  color: #333;
}

.cancel-btn:hover {
  background-color: #e0e0e0;
}

.message {
  margin-top: 15px;
  padding: 8px;
  border-radius: 4px;
}

.success {
  background-color: #dff0d8;
  color: #3c763d;
}

.error {
  background-color: #f2dede;
  color: #a94442;
}
</style> 