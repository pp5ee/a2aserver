<template>
  <div class="dialog-overlay" v-if="isOpen">
    <div class="dialog-container">
      <div class="dialog-header">
        <h2>API密钥设置</h2>
        <button class="close-button" @click="close" v-if="allowClose">
          <i class="material-icons">close</i>
        </button>
      </div>
      
      <div class="dialog-content">
        <p>您需要设置Google API密钥才能使用该应用程序。</p>
        
        <div class="input-group">
          <label for="dialog-api-key">Google API密钥</label>
          <input 
            type="password" 
            id="dialog-api-key" 
            v-model="localApiKey" 
            placeholder="输入您的API密钥"
            :disabled="usesVertexAi"
          />
        </div>
        
        <div class="checkbox-group">
          <input type="checkbox" id="dialog-vertex-ai" v-model="localUsesVertexAi" />
          <label for="dialog-vertex-ai">使用Vertex AI</label>
        </div>
        
        <div class="helper-text">
          <template v-if="localUsesVertexAi">
            选择此选项将使用Google Cloud Vertex AI身份验证。请确保已正确配置环境变量。
          </template>
          <template v-else>
            请从Google AI Studio获取API密钥以使用生成式AI功能。
          </template>
        </div>
      </div>
      
      <div class="dialog-actions">
        <button 
          class="save-button" 
          @click="saveApiKey"
          :disabled="!canSave"
        >
          保存
        </button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import { useStore } from 'vuex';

export default defineComponent({
  name: 'ApiKeyDialog',
  
  props: {
    isOpen: {
      type: Boolean,
      required: true
    },
    allowClose: {
      type: Boolean,
      default: true
    }
  },
  
  emits: ['close', 'save'],
  
  setup(props, { emit }) {
    const store = useStore();
    
    // 本地状态
    const localApiKey = ref(store.state.apiKey || '');
    const localUsesVertexAi = ref(store.state.usesVertexAi || false);
    
    // 当apiKey从store改变时更新本地状态
    watch(() => store.state.apiKey, (newValue) => {
      localApiKey.value = newValue;
    });
    
    watch(() => store.state.usesVertexAi, (newValue) => {
      localUsesVertexAi.value = newValue;
    });
    
    // 检查是否可以保存
    const canSave = computed(() => {
      return localUsesVertexAi.value || (localApiKey.value && localApiKey.value.trim() !== '');
    });
    
    // 保存API密钥
    const saveApiKey = async () => {
      try {
        if (localUsesVertexAi.value) {
          // 设置为使用Vertex AI
          store.commit('setUsesVertexAi', true);
          store.commit('setApiKey', '');
        } else {
          // 使用API密钥
          await store.dispatch('updateApiKey', localApiKey.value);
        }
        
        emit('save');
        emit('close');
      } catch (error) {
        console.error('Failed to save API key:', error);
        alert('保存API密钥失败');
      }
    };
    
    // 关闭对话框
    const close = () => {
      emit('close');
    };
    
    return {
      localApiKey,
      localUsesVertexAi,
      canSave,
      saveApiKey,
      close
    };
  }
});
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.dialog-container {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e0e0e0;
}

.dialog-header h2 {
  margin: 0;
  font-size: 20px;
  color: #333;
}

.close-button {
  background: none;
  border: none;
  cursor: pointer;
  color: #666;
}

.dialog-content {
  padding: 20px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid #e0e0e0;
}

.input-group {
  margin-bottom: 16px;
}

.input-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: bold;
  color: #555;
}

input[type="password"] {
  width: 100%;
  padding: 10px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 16px;
  box-sizing: border-box;
}

input[type="password"]:focus {
  border-color: #42b983;
  outline: none;
}

.checkbox-group {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
  gap: 8px;
}

.helper-text {
  font-size: 14px;
  color: #666;
  margin-bottom: 16px;
}

.save-button {
  padding: 10px 20px;
  background-color: #42b983;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

.save-button:hover {
  background-color: #3aa876;
}

.save-button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}
</style> 