<template>
  <div class="conversation-view">
    <div class="content-container">
      <div class="header">
        <h1>对话</h1>
        <div class="icon">
          <i class="material-icons">chat</i>
        </div>
      </div>
      
      <div class="chat-container">
        <!-- 消息区域 -->
        <div class="messages-area">
          <div 
            v-for="message in messages" 
            :key="message.messageId"
            :class="['message-bubble', message.role === 'user' ? 'user-message' : 'agent-message']"
          >
            <!-- 针对不同内容类型显示不同内容 -->
            <div v-for="(part, index) in message.content" :key="index">
              <!-- 文本内容 -->
              <div v-if="part.mediaType === 'text/plain'" class="text-content">
                <div v-html="formatMarkdown(part.content.toString())"></div>
              </div>
              
              <!-- 图片内容 -->
              <div v-else-if="part.mediaType.startsWith('image/')" class="image-content">
                <img :src="getImageSrc(part.content)" alt="Image" />
              </div>
              
              <!-- JSON/数据内容 -->
              <div v-else-if="part.mediaType === 'application/json'" class="json-content">
                <pre>{{ JSON.stringify(part.content, null, 2) }}</pre>
              </div>
              
              <!-- 表单内容 -->
              <div v-else-if="part.mediaType === 'form'" class="form-content">
                <div>表单已提交</div>
              </div>
            </div>
            
            <!-- 加载指示器 -->
            <div v-if="isProcessing(message.messageId)" class="processing-indicator">
              <div class="processing-text">{{ getProcessingText(message.messageId) || '处理中...' }}</div>
              <div class="progress-bar"></div>
            </div>
          </div>
        </div>
        
        <!-- 输入区域 -->
        <div class="input-area">
          <input 
            v-model="messageContent" 
            class="message-input" 
            placeholder="有什么可以帮助你的？"
            @keyup.enter="sendMessage"
          />
          <button class="send-button" @click="sendMessage">
            <i class="material-icons">send</i>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useStore } from 'vuex';
import { useRoute, useRouter } from 'vue-router';
import { v4 as uuidv4 } from 'uuid';

export default defineComponent({
  name: 'ConversationView',
  
  setup() {
    const store = useStore();
    const route = useRoute();
    const router = useRouter();
    
    // 消息内容
    const messageContent = ref('');
    
    // 轮询间隔
    let pollingInterval: number | null = null;
    
    // 初始化
    onMounted(() => {
      // 从查询参数获取会话ID
      const conversationId = route.query.conversation_id as string;
      
      if (conversationId) {
        // 设置当前会话ID
        store.commit('setCurrentConversationId', conversationId);
        
        // 加载消息
        store.dispatch('fetchMessages');
        
        // 启动轮询
        startPolling();
      } else {
        // 没有会话ID，重定向到首页
        router.push('/');
      }
    });
    
    // 组件卸载时清除轮询
    onUnmounted(() => {
      stopPolling();
    });
    
    // 监听会话ID变化
    watch(() => route.query.conversation_id, (newId) => {
      if (newId) {
        store.commit('setCurrentConversationId', newId as string);
        store.dispatch('fetchMessages');
      }
    });
    
    // 获取消息列表
    const messages = computed(() => {
      return store.state.messages;
    });
    
    // 启动轮询
    const startPolling = () => {
      stopPolling();
      pollingInterval = window.setInterval(() => {
        store.dispatch('pollUpdates');
      }, store.state.pollingInterval * 1000);
    };
    
    // 停止轮询
    const stopPolling = () => {
      if (pollingInterval !== null) {
        clearInterval(pollingInterval);
        pollingInterval = null;
      }
    };
    
    // 发送消息
    const sendMessage = () => {
      if (!messageContent.value.trim()) return;
      
      const messageId = uuidv4();
      store.dispatch('sendMessage', {
        content: messageContent.value,
        messageId
      });
      
      // 清空输入框
      messageContent.value = '';
    };
    
    // 检查消息是否正在处理中
    const isProcessing = (messageId: string) => {
      // 移除对 backgroundTasks 的依赖，只使用 messageAliases
      return Object.values(store.state.messageAliases).includes(messageId);
    };
    
    // 获取处理状态文本
    const getProcessingText = (messageId: string) => {
      // 返回固定文本
      return '处理中...';
    };
    
    // 格式化Markdown文本
    const formatMarkdown = (text: string) => {
      // 简单的Markdown格式化 - 这里只是示例，实际应用中可以使用第三方库
      return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/```([^`]+)```/g, '<pre>$1</pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
    };
    
    // 获取图片源
    const getImageSrc = (content: string | object) => {
      if (typeof content === 'string') {
        if (content.startsWith('data:') || content.startsWith('/')) {
          return content;
        }
        return `data:image/png;base64,${content}`;
      }
      return '';
    };
    
    return {
      messageContent,
      messages,
      sendMessage,
      isProcessing,
      getProcessingText,
      formatMarkdown,
      getImageSrc
    };
  }
});
</script>

<style scoped>
.conversation-view {
  min-height: 100vh;
  padding: 20px;
}

.content-container {
  max-width: 1200px;
  margin: 0 auto;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
  padding: 20px;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 100px);
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

.chat-container {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  height: 100%;
}

.messages-area {
  flex-grow: 1;
  overflow-y: auto;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.message-bubble {
  max-width: 80%;
  padding: 10px 15px;
  border-radius: 15px;
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
  margin-bottom: 10px;
}

.user-message {
  align-self: flex-end;
  background-color: #e3f2fd; /* 主题主容器色 */
}

.agent-message {
  align-self: flex-start;
  background-color: #f1f8e9; /* 主题次容器色 */
}

.text-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.image-content img {
  max-width: 100%;
  max-height: 300px;
  object-fit: contain;
}

.json-content pre {
  white-space: pre-wrap;
  background-color: #f5f5f5;
  padding: 10px;
  border-radius: 4px;
  overflow-x: auto;
}

.form-content {
  background-color: #f5f5f5;
  padding: 10px;
  border-radius: 4px;
}

.processing-indicator {
  margin-top: 10px;
  padding: 10px;
  background-color: #f5f5f5;
  border-radius: 4px;
}

.processing-text {
  margin-bottom: 5px;
  font-size: 14px;
  color: #666;
}

.progress-bar {
  height: 4px;
  width: 100%;
  background-color: #e0e0e0;
  border-radius: 2px;
  position: relative;
  overflow: hidden;
}

.progress-bar::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 30%;
  background-color: #42b983;
  animation: progress 1.5s infinite linear;
}

@keyframes progress {
  0% {
    left: -30%;
  }
  100% {
    left: 100%;
  }
}

.input-area {
  display: flex;
  padding: 15px 0;
  gap: 10px;
  border-top: 1px solid #e0e0e0;
}

.message-input {
  flex-grow: 1;
  padding: 12px 15px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 16px;
  outline: none;
  transition: border-color 0.2s;
}

.message-input:focus {
  border-color: #42b983;
}

.send-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  background-color: #42b983;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.send-button:hover {
  background-color: #3aa876;
}

.material-icons {
  font-size: 24px;
}
</style> 