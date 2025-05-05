<template>
  <div class="settings-view">
    <div class="content-container">
      <div class="header">
        <h1>设置</h1>
        <div class="icon">
          <i class="material-icons">settings</i>
        </div>
      </div>
      
      <div class="settings-section">
        <h2>API密钥设置</h2>
        <div class="setting-item">
          <label for="api-key">Google API密钥</label>
          <div class="input-group">
            <input 
              type="password" 
              id="api-key" 
              v-model="apiKey" 
              placeholder="输入Google API密钥"
              :disabled="usesVertexAi"
            />
            <button class="save-button" @click="updateApiKey" :disabled="usesVertexAi">
              保存
            </button>
          </div>
          <div class="helper-text">
            用于访问Google生成式AI服务的API密钥
          </div>
        </div>
        
        <div class="setting-item">
          <div class="checkbox-group">
            <input type="checkbox" id="use-vertex-ai" v-model="usesVertexAi" />
            <label for="use-vertex-ai">使用Vertex AI</label>
          </div>
          <div class="helper-text">
            启用此选项将使用Google Cloud Vertex AI服务而不是API密钥
          </div>
        </div>
      </div>
      
      <div class="settings-section">
        <h2>界面设置</h2>
        <div class="setting-item">
          <label for="theme-mode">主题模式</label>
          <select id="theme-mode" v-model="themeMode">
            <option value="system">跟随系统</option>
            <option value="light">浅色</option>
            <option value="dark">深色</option>
          </select>
        </div>
        
        <div class="setting-item">
          <label for="polling-interval">轮询间隔（秒）</label>
          <input 
            type="number" 
            id="polling-interval" 
            v-model.number="pollingInterval" 
            min="1" 
            max="10"
          />
          <div class="helper-text">
            更新消息和状态的频率（秒）
          </div>
        </div>
      </div>
    </div>
    
    <!-- 添加操作结果提示 -->
    <div class="toast" v-if="toast.show">
      <div class="toast-content" :class="toast.type">
        {{ toast.message }}
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, reactive } from 'vue';
import { useStore } from 'vuex';
import { apiService } from '@/services/api';

interface ToastState {
  show: boolean;
  message: string;
  type: 'success' | 'error';
}

export default defineComponent({
  name: 'SettingsView',
  
  setup() {
    const store = useStore();
    
    // 从状态获取初始值
    const apiKey = ref(store.state.apiKey);
    const usesVertexAi = ref(store.state.usesVertexAi);
    const themeMode = ref(store.state.themeMode);
    const pollingInterval = ref(store.state.pollingInterval);
    
    // 提示消息状态
    const toast = reactive<ToastState>({
      show: false,
      message: '',
      type: 'success'
    });
    
    // 显示提示消息
    const showToast = (message: string, type: 'success' | 'error' = 'success') => {
      toast.message = message;
      toast.type = type;
      toast.show = true;
      
      // 3秒后自动关闭
      setTimeout(() => {
        toast.show = false;
      }, 3000);
    };
    
    // 更新API密钥
    const updateApiKey = async () => {
      if (!apiKey.value.trim()) return;
      
      try {
        await store.dispatch('updateApiKey', apiKey.value);
        showToast('API密钥已更新');
      } catch (error) {
        console.error('更新API密钥失败:', error);
        showToast('更新API密钥失败', 'error');
      }
    };
    
    // 监听主题模式变化
    const watchThemeMode = computed({
      get: () => themeMode.value,
      set: (value) => {
        themeMode.value = value;
        store.commit('setThemeMode', value);
        // 可以在这里应用主题变化
        document.documentElement.setAttribute('data-theme', value);
      }
    });
    
    // 监听轮询间隔变化
    const watchPollingInterval = computed({
      get: () => pollingInterval.value,
      set: (value) => {
        if (value < 1) value = 1;
        if (value > 10) value = 10;
        pollingInterval.value = value;
        store.commit('setPollingInterval', value);
      }
    });
    
    return {
      apiKey,
      usesVertexAi,
      themeMode: watchThemeMode,
      pollingInterval: watchPollingInterval,
      toast,
      updateApiKey
    };
  }
});
</script>

<style scoped>
.settings-view {
  min-height: 100vh;
  padding: 20px;
  position: relative;
}

.content-container {
  max-width: 800px;
  margin: 0 auto;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
  padding: 20px;
}

.header {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e0e0e0;
}

.header h1 {
  margin: 0;
  font-size: 24px;
}

.header .icon {
  margin-left: 10px;
  display: flex;
  align-items: center;
}

.settings-section {
  margin-bottom: 30px;
}

.settings-section h2 {
  font-size: 18px;
  margin-bottom: 15px;
  color: #333;
}

.setting-item {
  margin-bottom: 20px;
}

.setting-item label {
  display: block;
  margin-bottom: 8px;
  font-weight: bold;
  color: #555;
}

.input-group {
  display: flex;
  gap: 10px;
}

input[type="text"],
input[type="password"],
input[type="number"],
select {
  padding: 10px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 16px;
  width: 100%;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

input[type="text"]:focus,
input[type="password"]:focus,
input[type="number"]:focus,
select:focus {
  border-color: #42b983;
  outline: none;
}

.save-button {
  padding: 10px 20px;
  background-color: #42b983;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
  transition: background-color 0.2s;
  white-space: nowrap;
}

.save-button:hover {
  background-color: #3aa876;
}

.save-button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.helper-text {
  font-size: 14px;
  color: #666;
  margin-top: 5px;
}

.checkbox-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.checkbox-group label {
  margin-bottom: 0;
}

/* 代理列表样式 */
.agent-list {
  margin-top: 20px;
  border-top: 1px solid #e0e0e0;
  padding-top: 15px;
}

.agent-list h3 {
  font-size: 16px;
  margin-bottom: 10px;
  color: #333;
}

.agent-list ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.agent-list li {
  padding: 10px;
  background-color: #f9f9f9;
  border-radius: 4px;
  margin-bottom: 8px;
}

.agent-info {
  display: flex;
  flex-direction: column;
}

.agent-name {
  font-weight: bold;
  margin-bottom: 4px;
}

.agent-url {
  font-size: 13px;
  color: #666;
}

.no-agents {
  color: #999;
  font-style: italic;
  margin-top: 15px;
}

/* 提示消息样式 */
.toast {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
}

.toast-content {
  padding: 12px 20px;
  border-radius: 4px;
  color: white;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
}

.toast-content.success {
  background-color: #42b983;
}

.toast-content.error {
  background-color: #e53935;
}
</style> 