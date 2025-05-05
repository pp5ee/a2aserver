<template>
  <div class="home">
    <div class="content-container">
      <div class="header">
        <h1>对话列表</h1>
        <div class="icon">
          <i class="material-icons">message</i>
        </div>
      </div>
      
      <!-- 添加消息提示 -->
      <div v-if="notification.show" :class="['notification', notification.type]">
        {{ notification.message }}
        <button class="close-notification" @click="notification.show = false">&times;</button>
      </div>
      
      <div class="conversation-list">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>名称</th>
              <th>状态</th>
              <th>消息数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr 
              v-for="conversation in conversations" 
              :key="conversation.conversationId"
              class="conversation-row"
            >
              <td @click="openConversation(conversation.conversationId)">{{ conversation.conversationId }}</td>
              <td @click="openConversation(conversation.conversationId)">{{ conversation.conversationName || '无名称' }}</td>
              <td @click="openConversation(conversation.conversationId)">{{ conversation.isActive ? '开启' : '关闭' }}</td>
              <td @click="openConversation(conversation.conversationId)">{{ conversation.messageIds.length }}</td>
              <td>
                <button class="delete-btn" @click.stop="confirmDelete(conversation)">
                  <i class="material-icons">delete</i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        
        <button class="new-conversation-btn" @click="createNewConversation">
          <i class="material-icons">add</i> 新建对话
        </button>
      </div>
    </div>
    
    <!-- 删除确认对话框 -->
    <div v-if="deleteDialog.show" class="delete-dialog-backdrop">
      <div class="delete-dialog">
        <h3>删除会话</h3>
        <p>确定要删除这个会话吗？此操作无法撤销。</p>
        <div class="dialog-actions">
          <button class="cancel-btn" @click="deleteDialog.show = false">取消</button>
          <button class="confirm-btn" @click="deleteConversation">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, computed, onMounted, ref, reactive } from 'vue';
import { useStore } from 'vuex';
import { useRouter } from 'vue-router';
import { v4 as uuidv4 } from 'uuid';
import { apiService } from '../services/api';

export default defineComponent({
  name: 'HomeView',
  
  setup() {
    const store = useStore();
    const router = useRouter();
    
    // 通知消息
    const notification = reactive({
      show: false,
      message: '',
      type: 'success', // success, error
      timeout: null as number | null
    });
    
    // 显示通知
    const showNotification = (message: string, type: string = 'success') => {
      // 清除之前的定时器
      if (notification.timeout) {
        clearTimeout(notification.timeout);
      }
      
      notification.message = message;
      notification.type = type;
      notification.show = true;
      
      // 5秒后自动关闭
      notification.timeout = setTimeout(() => {
        notification.show = false;
      }, 5000) as unknown as number;
    };
    
    // 删除对话框
    const deleteDialog = reactive({
      show: false,
      conversationId: ''
    });
    
    // 确认删除对话
    const confirmDelete = (conversation: any) => {
      deleteDialog.conversationId = conversation.conversationId;
      deleteDialog.show = true;
    };
    
    // 删除会话
    const deleteConversation = async () => {
      try {
        const response = await apiService.deleteConversation(deleteDialog.conversationId);
        
        if (response.data && response.data.status === 'success') {
          // 更新会话列表
          store.dispatch('fetchConversations');
          showNotification(response.data.message || '会话删除成功');
        } else {
          // 处理各种错误类型
          const errorMsg = response.data.error || '删除会话失败';
          const errorCode = response.data.code || 500;
          
          // 根据错误码提供更友好的提示
          if (errorCode === 401) {
            showNotification('请先连接钱包后再操作', 'error');
          } else if (errorCode === 403) {
            showNotification('您没有权限删除此会话', 'error');
          } else {
            showNotification(errorMsg, 'error');
          }
        }
      } catch (error: any) {
        console.error('删除会话出错', error);
        
        // 检查是否有响应数据
        if (error.response && error.response.data) {
          const errorData = error.response.data;
          showNotification(errorData.error || '删除会话时发生错误', 'error');
        } else {
          showNotification('删除会话时连接服务器失败', 'error');
        }
      } finally {
        // 关闭对话框
        deleteDialog.show = false;
      }
    };
    
    // 初始化页面数据
    onMounted(() => {
      // 加载对话列表
      store.dispatch('fetchConversations');
      
      // 启动轮询
      const pollingInterval = setInterval(() => {
        store.dispatch('pollUpdates');
      }, store.state.pollingInterval * 1000);
      
      // 组件卸载时清除轮询
      return () => {
        clearInterval(pollingInterval);
      };
    });
    
    // 获取对话列表
    const conversations = computed(() => {
      return store.state.conversations;
    });
    
    // 创建新对话
    const createNewConversation = async () => {
      try {
        const result = await store.dispatch('createConversation');
        
        if (result && result.error) {
          // 如果有错误信息，显示通知
          showNotification(result.error, 'error');
          return;
        }
        
        const conversationId = result;
        if (conversationId) {
          router.push({
            name: 'conversation',
            query: { conversation_id: conversationId }
          });
        }
      } catch (error) {
        console.error('创建会话出错', error);
        showNotification('创建会话时发生错误', 'error');
      }
    };
    
    // 打开现有对话
    const openConversation = (conversationId: string) => {
      store.commit('setCurrentConversationId', conversationId);
      router.push({
        name: 'conversation',
        query: { conversation_id: conversationId }
      });
    };
    
    return {
      conversations,
      createNewConversation,
      openConversation,
      deleteDialog,
      confirmDelete,
      deleteConversation,
      notification
    };
  }
});
</script>

<style scoped>
.home {
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
  position: relative;
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

table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 20px;
}

th, td {
  padding: 12px 15px;
  text-align: left;
  border-bottom: 1px solid #e0e0e0;
}

th {
  background-color: #f5f5f5;
  font-weight: bold;
  position: sticky;
  top: 0;
}

.conversation-row {
  transition: background-color 0.2s;
}

.conversation-row:hover {
  background-color: #f5f5f5;
}

.conversation-row td:not(:last-child) {
  cursor: pointer;
}

.delete-btn {
  background: none;
  border: none;
  color: #f44336;
  cursor: pointer;
  padding: 5px;
  border-radius: 50%;
  transition: background-color 0.2s;
}

.delete-btn:hover {
  background-color: rgba(244, 67, 54, 0.1);
}

.new-conversation-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 10px 20px;
  background-color: #42b983;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
  transition: background-color 0.2s;
  margin-top: 10px;
}

.new-conversation-btn:hover {
  background-color: #3aa876;
}

.material-icons {
  font-size: 24px;
}

/* 删除确认对话框 */
.delete-dialog-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.delete-dialog {
  background-color: white;
  border-radius: 8px;
  padding: 20px;
  max-width: 400px;
  width: 90%;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.delete-dialog h3 {
  margin-top: 0;
  color: #333;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
  gap: 10px;
}

.cancel-btn {
  background-color: #f5f5f5;
  color: #333;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.confirm-btn {
  background-color: #f44336;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

/* 通知 */
.notification {
  position: absolute;
  top: -60px;
  left: 0;
  right: 0;
  margin: 0 auto;
  width: 80%;
  max-width: 500px;
  padding: 15px;
  border-radius: 4px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  animation: slideDown 0.3s forwards;
  z-index: 100;
}

.notification.success {
  background-color: #4CAF50;
  color: white;
}

.notification.error {
  background-color: #f44336;
  color: white;
}

.close-notification {
  background: none;
  border: none;
  color: white;
  font-size: 20px;
  cursor: pointer;
  padding: 0 5px;
}

@keyframes slideDown {
  from { transform: translateY(0); }
  to { transform: translateY(80px); }
}
</style> 