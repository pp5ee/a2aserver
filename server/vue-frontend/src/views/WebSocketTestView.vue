<template>
  <div class="ws-test-container">
    <div class="header">
      <h1>WebSocket测试</h1>
      <div class="ws-status" :class="{ connected: wsConnected }">
        {{ wsConnected ? 'WebSocket已连接' : 'WebSocket未连接' }}
      </div>
      
      <!-- 添加WebSocket测试功能 -->
      <div class="ws-test-actions">
        <button @click="testWebSocketConnection" class="test-btn" :disabled="!walletConnected">
          测试WebSocket连接
        </button>
        <span v-if="connectionTestResult" 
              class="test-result" 
              :class="{'success': connectionTestResult.success, 'error': !connectionTestResult.success}">
          {{ connectionTestResult.message }}
        </span>
      </div>
    </div>

    <div class="content">
      <!-- 会话列表 -->
      <div class="conversations-panel">
        <h2>会话列表</h2>
        <div v-if="loading.conversations" class="loading">加载中...</div>
        <template v-else>
          <div v-if="conversations.length === 0" class="empty-list">暂无会话</div>
          <div 
            v-for="conv in conversations" 
            :key="conv.conversation_id" 
            @click="selectConversation(conv.conversation_id)"
            class="conversation-item"
            :class="{ active: currentConversationId === conv.conversation_id }"
          >
            <div class="conversation-title">{{ conv.name || '会话 ' + (conv.conversation_id ? conv.conversation_id.slice(0, 8) : '') }}</div>
            <div class="conversation-id">ID: {{ conv.conversation_id ? conv.conversation_id.slice(0, 8) + '...' : 'N/A' }}</div>
            <!-- 显示会话中的消息数量 -->
            <div class="conversation-message-count" v-if="conv.message_count !== undefined">
              {{ conv.message_count }} 条消息
            </div>
          </div>
          <button @click="createNewConversation" class="create-btn">创建新会话</button>
        </template>
      </div>

      <!-- 消息面板 -->
      <div class="messages-panel">
        <div v-if="!currentConversationId" class="select-prompt">
          请选择一个会话
        </div>
        <template v-else>
          <h2>消息 - {{ getConversationName() }}</h2>
          
          <!-- 消息列表 -->
          <div class="message-container" ref="messageContainer">
            <div v-if="loading.messages" class="loading">加载消息中...</div>
            <div v-else-if="messages.length === 0" class="empty-list">暂无消息</div>
            
            <div v-for="(message, index) in messages" :key="message.id || index" class="message-wrapper">
              <!-- 消息内容 -->
              <div class="message" :class="message.role">
                <div class="message-header">
                  <span class="role">{{ getRoleName(message.role) }}</span>
                  <span class="timestamp" v-if="message.timestamp">{{ formatTimestamp(message.timestamp) }}</span>
                </div>
                <div class="message-body">
                  <div v-for="(part, partIndex) in message.parts" :key="partIndex" class="message-part">
                    <div v-if="part.type === 'text'" class="text-part">{{ part.text }}</div>
                    <div v-else-if="part.type === 'data'" class="data-part">
                      <pre>{{ JSON.stringify(part.data, null, 2) }}</pre>
                    </div>
                    <div v-else class="unknown-part">不支持的内容类型: {{ part.type }}</div>
                  </div>
                </div>
              </div>
              
              <!-- Agent Loading 状态指示器 -->
              <div v-if="message.role === 'user' && isWaitingForAgentResponse(message)" class="agent-loading">
                <div class="loading-spinner"></div>
                <span>Agent 正在处理...</span>
              </div>
              
              <!-- 任务状态及产出物 (如果有) -->
              <div v-if="getTaskForMessage(message)" class="task-info">
                <div class="task-status">
                  <span class="task-state" :class="getTaskStateClass(getTaskForMessage(message)?.status?.state || '')">
                    状态: {{ getTaskForMessage(message)?.status?.state || 'unknown' }}
                  </span>
                  <span class="task-message" v-if="getTaskForMessage(message)?.status?.message">
                    {{ getTaskForMessage(message)?.status?.message }}
                  </span>
                </div>
                
                <!-- 任务产出物 -->
                <div v-if="getTaskForMessage(message) && getTaskForMessage(message).artifacts && getTaskForMessage(message).artifacts.length > 0" class="task-artifacts">
                  <h4>产出物:</h4>
                  <div v-for="(artifact, artifactIndex) in getTaskForMessage(message)?.artifacts || []" :key="artifactIndex" class="artifact">
                    <div class="artifact-name">{{ artifact.name }}</div>
                    <div class="artifact-content">
                      <div v-for="(part, partIndex) in artifact.parts" :key="partIndex">
                        <div v-if="part.type === 'text'" class="text-part">{{ part.text }}</div>
                      </div>
                    </div>
                  </div>
                </div>
                
                <!-- 任务历史记录 -->
                <div v-if="getTaskForMessage(message) && getTaskForMessage(message).history && getTaskForMessage(message).history.length > 0" class="task-history">
                  <h4>任务历史:</h4>
                  <div v-for="(historyItem, historyIndex) in getTaskForMessage(message)?.history || []" :key="historyIndex" class="history-item">
                    <div class="history-role">{{ getRoleName(historyItem.role) }}</div>
                    <div class="history-content">
                      <div v-for="(part, partIndex) in historyItem.parts" :key="partIndex">
                        <div v-if="part.type === 'text'" class="text-part">{{ part.text }}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 消息输入框 -->
          <div class="message-input">
            <textarea 
              v-model="newMessage" 
              placeholder="输入消息..." 
              @keyup.ctrl.enter="sendMessage"
              @keyup.meta.enter="sendMessage"
            ></textarea>
            <button @click="sendMessage" :disabled="!newMessage.trim() || sending">
              {{ sending ? '发送中...' : '发送' }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import { apiService } from '../services/api';
import { webSocketService, NewMessageEvent, TaskUpdateEvent } from '../services/websocket';
import { getWalletAddress } from '../services/solana-wallet';

interface Conversation {
  conversation_id: string;
  name?: string;
  is_active?: boolean;
  message_count?: number;
}

interface MessagePart {
  type: string;
  text?: string;
  data?: any;
}

interface Message {
  id?: string;
  role: string;
  parts: MessagePart[];
  metadata?: any;
  timestamp?: string;
  waiting_for_response?: boolean;
}

interface TaskStatus {
  state: string;
  message: string;
  timestamp: string;
}

interface TaskArtifact {
  name: string;
  parts: Array<{
    type: string;
    text: string | null;
  }>;
}

// 自定义消息接口，包含元数据
interface TaskStatusMessage {
  metadata?: {
    message_id?: string;
  };
  text?: string;
}

interface Task {
  id: string;
  sessionId: string;
  status: {
    state: string;
    message: string | TaskStatusMessage;
    timestamp: string;
  };
  artifacts?: TaskArtifact[];
  messageId?: string;
  history?: Array<{
    role: string;
    parts: Array<{
      type: string;
      text: string | null;
    }>;
    metadata?: {
      message_id?: string;
    };
  }>;
}

export default defineComponent({
  name: 'WebSocketTestView',
  
  data() {
    return {
      conversations: [] as Conversation[],
      currentConversationId: '',
      messages: [] as Message[],
      tasks: [] as Task[],
      messageTasks: {} as Record<string, Task>, // 消息ID到任务的映射
      messageResponses: {} as Record<string, boolean>, // 跟踪哪些用户消息已收到回复
      newMessage: '',
      wsConnected: false,
      walletConnected: false, // 添加钱包连接状态
      sending: false,
      loading: {
        conversations: false,
        messages: false,
        tasks: false
      },
      connectionTestResult: null as { success: boolean, message: string } | null,
    };
  },
  
  async created() {
    // 加载会话列表
    this.loadConversations();
    
    // 设置WebSocket监听器
    this.setupWebSocketListeners();
    
    // 检查钱包连接状态
    this.checkWalletConnection();
  },
  
  beforeUnmount() {
    // 移除所有监听器并断开连接
    webSocketService.off('new_message');
    webSocketService.off('task_update');
    webSocketService.off('connection_established');
    webSocketService.disconnect();
  },
  
  methods: {
    // 加载会话列表
    async loadConversations() {
      this.loading.conversations = true;
      try {
        const response = await apiService.listConversations();
        if (response.data && response.data.result) {
          this.conversations = response.data.result.sort((a: Conversation, b: Conversation) => {
            return (b.is_active === a.is_active) ? 0 : b.is_active ? 1 : -1;
          });
        }
      } catch (error) {
        console.error('加载会话列表失败:', error);
      } finally {
        this.loading.conversations = false;
      }
    },
    
    // 获取会话名称
    getConversationName() {
      const conversation = this.conversations.find(c => c.conversation_id === this.currentConversationId);
      return conversation?.name || '会话 ' + (this.currentConversationId ? this.currentConversationId.slice(0, 8) : '');
    },
    
    // 创建新会话
    async createNewConversation() {
      try {
        const response = await apiService.createConversation();
        if (response.data && response.data.result) {
          const newConversation = response.data.result;
          this.conversations.unshift(newConversation);
          this.selectConversation(newConversation.conversation_id);
        }
      } catch (error) {
        console.error('创建会话失败:', error);
      }
    },
    
    // 选择会话
    async selectConversation(conversationId: string) {
      if (this.currentConversationId === conversationId) return;
      
      this.currentConversationId = conversationId;
      this.messages = [];
      this.tasks = [];
      this.messageTasks = {};
      this.messageResponses = {};
      
      // 加载历史消息
      await this.loadMessages();
      
      // 加载任务
      await this.loadTasks();
      
      // 建立WebSocket连接
      this.connectWebSocket();
      
      // 滚动到最新消息
      this.$nextTick(() => {
        this.scrollToBottom();
      });
    },
    
    // 加载消息
    async loadMessages() {
      if (!this.currentConversationId) return;
      
      this.loading.messages = true;
      try {
        const response = await apiService.listMessages(this.currentConversationId);
        if (response.data && response.data.result) {
          this.messages = response.data.result;
          
          // 分析已有的用户-代理消息对，更新messageResponses
          this.updateMessageResponseStatus();
        }
      } catch (error) {
        console.error('加载消息失败:', error);
      } finally {
        this.loading.messages = false;
      }
    },
    
    // 更新消息响应状态
    updateMessageResponseStatus() {
      // 重置状态
      this.messageResponses = {};
      
      // 遍历所有消息
      let lastUserMessageId = null;
      
      for (const message of this.messages) {
        if (message.role === 'user' && message.metadata && message.metadata.message_id) {
          lastUserMessageId = message.metadata.message_id;
          this.messageResponses[lastUserMessageId] = false;
        } else if (message.role !== 'user' && lastUserMessageId) {
          // 如果找到非用户的消息，将最后一个用户消息标记为已收到回复
          this.messageResponses[lastUserMessageId] = true;
          lastUserMessageId = null;
        }
      }
    },
    
    // 判断是否正在等待Agent回复
    isWaitingForAgentResponse(message: Message): boolean {
      if (message.role !== 'user' || !message.metadata || !message.metadata.message_id) {
        return false;
      }
      
      const messageId = message.metadata.message_id;
      return this.messageResponses[messageId] === false;
    },
    
    // 获取任务状态样式类
    getTaskStateClass(state?: string): string {
      if (!state) return '';
      
      switch (state.toLowerCase()) {
        case 'running':
          return 'state-running';
        case 'succeeded':
          return 'state-succeeded';
        case 'failed':
          return 'state-failed';
        case 'canceled':
          return 'state-canceled';
        default:
          return '';
      }
    },
    
    // 加载任务
    async loadTasks() {
      if (!this.currentConversationId) return;
      
      this.loading.tasks = true;
      try {
        const response = await apiService.listTasks(this.currentConversationId);
        if (response.data && response.data.result) {
          this.tasks = response.data.result;
          
          // 建立消息ID到任务的映射
          this.updateMessageTaskMapping();
        }
      } catch (error) {
        console.error('加载任务失败:', error);
      } finally {
        this.loading.tasks = false;
      }
    },
    
    // 更新消息ID到任务的映射
    updateMessageTaskMapping() {
      // 清空当前映射
      this.messageTasks = {};
      
      // 遍历所有任务
      for (const task of this.tasks) {
        // 检查任务状态消息
        if (task.status && task.status.message) {
          const message = task.status.message;
          // 如果消息是对象形式且包含metadata
          if (typeof message === 'object' && message.metadata && message.metadata.message_id) {
            const messageId = message.metadata.message_id;
            if (messageId) {
              this.messageTasks[messageId] = task;
              continue;
            }
          }
        }
        
        // 检查任务历史记录
        if (task.history) {
          for (const historyMessage of task.history) {
            if (historyMessage.metadata && historyMessage.metadata.message_id) {
              const messageId = historyMessage.metadata.message_id;
              this.messageTasks[messageId] = task;
            }
          }
        }
      }
    },
    
    // 获取消息对应的任务
    getTaskForMessage(message: Message): Task | null {
      if (!message || !message.metadata || !message.metadata.message_id) return null;
      
      const messageId = message.metadata.message_id;
      return this.messageTasks[messageId] || null;
    },
    
    // 发送消息
    async sendMessage() {
      if (!this.currentConversationId || !this.newMessage.trim() || this.sending) return;
      
      this.sending = true;
      try {
        // 生成唯一消息ID
        const messageId = this.generateUuid();
        
        // 创建消息对象
        const messageObj = {
          role: 'user',
          parts: [{ type: 'text', text: this.newMessage.trim() }],
          metadata: {
            conversation_id: this.currentConversationId,
            message_id: messageId
          }
        };
        
        // 添加到消息列表
        this.messages.push(messageObj);
        
        // 初始化消息响应状态为未响应
        this.messageResponses[messageId] = false;
        
        // 清空输入框
        const messageToBeSent = this.newMessage.trim();
        this.newMessage = '';
        
        // 滚动到底部
        this.$nextTick(() => {
          this.scrollToBottom();
        });
        
        // 发送消息
        await apiService.sendMessage(messageObj);
        
        // 立即加载任务
        setTimeout(() => {
          this.loadTasks();
        }, 500);
      } catch (error) {
        console.error('发送消息失败:', error);
      } finally {
        this.sending = false;
      }
    },
    
    // 连接WebSocket
    async connectWebSocket() {
      try {
        await webSocketService.connect();
        this.wsConnected = true;
      } catch (error) {
        console.error('WebSocket连接失败:', error);
        this.wsConnected = false;
      }
    },
    
    // 设置WebSocket监听器
    setupWebSocketListeners() {
      // 连接建立时
      webSocketService.on('connection_established', () => {
        this.wsConnected = true;
        console.log('WebSocket连接已建立');
      });
      
      // 新消息
      webSocketService.on<NewMessageEvent>('new_message', (data) => {
        console.log('收到新消息:', data);
        
        // 检查是否与当前会话相关
        if (data.conversation_id !== this.currentConversationId) return;
        
        // 检查消息是否已存在
        const existingMessageIndex = this.messages.findIndex(m => 
          m.metadata && m.metadata.message_id === data.message.id
        );
        
        if (existingMessageIndex === -1) {
          // 转换为消息格式
          const newMessage: Message = {
            id: data.message.id,
            role: data.message.role,
            parts: data.message.content.map(c => ({
              type: c.type,
              text: c.text || ''
            })),
            metadata: {
              message_id: data.message.id,
              conversation_id: data.conversation_id
            }
          };
          
          // 添加到消息列表
          this.messages.push(newMessage);
          
          // 更新消息响应状态
          this.updateAgentResponseReceived(newMessage);
          
          // 滚动到底部
          this.$nextTick(() => {
            this.scrollToBottom();
          });
        }
      });
      
      // 任务更新
      webSocketService.on<TaskUpdateEvent>('task_update', (data) => {
        console.log('收到任务更新:', data);
        
        // 检查是否与当前会话相关
        if (data.conversation_id !== this.currentConversationId) return;
        
        const task = data.task;
        
        // 检查任务是否已存在
        const existingTaskIndex = this.tasks.findIndex(t => t.id === task.id);
        
        if (existingTaskIndex !== -1) {
          // 更新现有任务，保留现有字段，并合并新数据
          this.tasks[existingTaskIndex] = {
            ...this.tasks[existingTaskIndex],
            status: task.status,
            artifacts: task.artifacts || this.tasks[existingTaskIndex].artifacts,
            history: task.history || this.tasks[existingTaskIndex].history
          };
          
          // 如果有message_id，更新关联
          if (data.message_id) {
            this.tasks[existingTaskIndex].messageId = data.message_id;
          }
        } else {
          // 添加新任务
          const newTask: Task = {
            id: task.id,
            sessionId: task.sessionId,
            status: task.status,
            artifacts: task.artifacts,
            history: task.history
          };
          
          // 如果有message_id，添加到任务对象中
          if (data.message_id) {
            newTask.messageId = data.message_id;
          }
          
          this.tasks.push(newTask);
        }
        
        // 如果有message_id，直接关联任务和消息
        if (data.message_id) {
          const taskIndex = existingTaskIndex !== -1 ? existingTaskIndex : this.tasks.length - 1;
          if (taskIndex >= 0 && taskIndex < this.tasks.length) {
            this.messageTasks[data.message_id] = this.tasks[taskIndex];
            console.log(`已关联消息 ${data.message_id} 和任务 ${task.id}`);
          }
        } else {
          // 如果没有message_id，使用现有逻辑
          this.updateMessageTaskMapping();
        }
        
        // 触发视图更新，刷新界面显示
        this.$forceUpdate();
      });
    },
    
    // 更新代理回复状态
    updateAgentResponseReceived(message: Message) {
      if (message.role !== 'user') {
        // 查找最后一条用户消息
        for (let i = this.messages.length - 1; i >= 0; i--) {
          const msg = this.messages[i];
          if (msg.role === 'user' && msg.metadata && msg.metadata.message_id) {
            // 设置此用户消息已收到回复
            this.messageResponses[msg.metadata.message_id] = true;
            break;
          }
        }
      }
    },
    
    // 滚动到底部
    scrollToBottom() {
      const container = this.$refs.messageContainer as HTMLElement;
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    },
    
    // 格式化时间戳
    formatTimestamp(timestamp: string): string {
      try {
        const date = new Date(timestamp);
        return date.toLocaleString();
      } catch (e) {
        return timestamp;
      }
    },
    
    // 获取角色名称
    getRoleName(role: string): string {
      switch (role) {
        case 'user': return '用户';
        case 'agent': return '代理';
        case 'model': return '模型';
        default: return role;
      }
    },
    
    // 生成UUID
    generateUuid(): string {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
      });
    },
    
    // 检查钱包连接状态
    checkWalletConnection() {
      const address = getWalletAddress();
      this.walletConnected = !!address;
    },
    
    // 测试WebSocket连接
    async testWebSocketConnection() {
      // 重置测试结果
      this.connectionTestResult = null;
      
      try {
        // 确保钱包已连接
        if (!getWalletAddress()) {
          this.connectionTestResult = { 
            success: false, 
            message: '请先连接钱包' 
          };
          return;
        }
        
        // 尝试连接WebSocket
        await webSocketService.connect();
        this.wsConnected = true;
        
        // 记录测试信息
        console.log('测试WebSocket连接 - 连接成功');
        
        // 添加一个一次性监听器，检查是否收到连接成功的消息
        let receivedConnectionMessage = false;
        let testTimeout: number | null = null;
        
        const connectionListener = () => {
          receivedConnectionMessage = true;
          if (testTimeout !== null) clearTimeout(testTimeout);
          this.connectionTestResult = {
            success: true,
            message: 'WebSocket连接测试成功，收到服务器确认'
          };
        };
        
        // 添加一次性消息监听
        webSocketService.on('connection_established', connectionListener);
        
        // 设置超时（5秒）
        testTimeout = window.setTimeout(() => {
          // 确保在正确的类型下操作
          if (typeof webSocketService !== 'undefined' && webSocketService) {
            webSocketService.off('connection_established', connectionListener);
          }
          
          if (!receivedConnectionMessage) {
            this.connectionTestResult = {
              success: this.wsConnected,
              message: this.wsConnected ? 
                '连接已建立，但未收到服务器确认消息' : 
                'WebSocket连接失败'
            };
          }
        }, 5000);
        
      } catch (error) {
        console.error('WebSocket连接测试失败:', error);
        this.wsConnected = false;
        this.connectionTestResult = {
          success: false,
          message: `连接失败: ${error instanceof Error ? error.message : String(error)}`
        };
      }
    },
  }
});
</script>

<style scoped>
.ws-test-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px;
  font-family: Arial, sans-serif;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h1 {
  margin: 0;
}

.ws-status {
  padding: 8px 16px;
  border-radius: 20px;
  background-color: #ffebee;
  color: #d32f2f;
  font-weight: bold;
}

.ws-status.connected {
  background-color: #e8f5e9;
  color: #2e7d32;
}

.content {
  display: flex;
  height: calc(100vh - 100px);
}

.conversations-panel {
  width: 300px;
  border-right: 1px solid #e0e0e0;
  padding-right: 20px;
  overflow-y: auto;
}

.messages-panel {
  flex: 1;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
}

.message-container {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 20px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 10px;
}

.conversation-item {
  padding: 10px;
  border-radius: 8px;
  margin-bottom: 10px;
  cursor: pointer;
  background-color: #f5f5f5;
}

.conversation-item:hover {
  background-color: #eeeeee;
}

.conversation-item.active {
  background-color: #e3f2fd;
  border-left: 4px solid #2196f3;
}

.conversation-title {
  font-weight: bold;
  margin-bottom: 5px;
}

.conversation-id {
  font-size: 12px;
  color: #757575;
}

.conversation-message-count {
  font-size: 11px;
  color: #757575;
  margin-top: 5px;
}

.message-wrapper {
  margin-bottom: 20px;
}

.message {
  padding: 12px;
  border-radius: 8px;
  max-width: 80%;
}

.message.user {
  background-color: #e3f2fd;
  margin-left: auto;
}

.message.agent, .message.model {
  background-color: #f5f5f5;
  margin-right: auto;
}

.message-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.role {
  font-weight: bold;
}

.timestamp {
  font-size: 12px;
  color: #757575;
}

.message-body {
  word-break: break-word;
}

.message-part {
  margin-bottom: 8px;
}

.test-result {
  margin-left: 10px;
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 14px;
}

.test-result.success {
  background-color: #e8f5e9;
  color: #2e7d32;
}

.test-result.error {
  background-color: #ffebee;
  color: #d32f2f;
}

.message-input {
  display: flex;
  margin-top: 10px;
}

.message-input textarea {
  flex: 1;
  height: 80px;
  padding: 10px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  resize: none;
  margin-right: 10px;
}

.message-input button {
  padding: 0 20px;
  background-color: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.message-input button:hover {
  background-color: #1976d2;
}

.message-input button:disabled {
  background-color: #bdbdbd;
  cursor: not-allowed;
}

.test-btn {
  padding: 8px 16px;
  background-color: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.test-btn:disabled {
  background-color: #bdbdbd;
  cursor: not-allowed;
}

.create-btn {
  padding: 8px 16px;
  background-color: #4caf50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  margin-top: 10px;
  width: 100%;
}

.create-btn:hover {
  background-color: #388e3c;
}

.empty-list {
  text-align: center;
  padding: 20px;
  color: #757575;
}

.select-prompt {
  text-align: center;
  padding: 40px;
  color: #757575;
  font-size: 18px;
}

.loading {
  text-align: center;
  padding: 20px;
  color: #757575;
}

.task-info {
  margin-top: 10px;
  padding: 10px;
  border-radius: 4px;
  background-color: #f9f9f9;
  font-size: 14px;
}

.task-status {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.task-state {
  font-weight: bold;
  margin-right: 10px;
}

.state-running {
  color: #2196f3;
}

.state-succeeded {
  color: #4caf50;
}

.state-failed {
  color: #f44336;
}

.state-canceled {
  color: #ff9800;
}

.task-message {
  color: #616161;
}

.task-artifacts, .task-history {
  margin-top: 10px;
}

.artifact, .history-item {
  margin-bottom: 8px;
  padding: 8px;
  background-color: #f5f5f5;
  border-radius: 4px;
}

.artifact-name, .history-role {
  font-weight: bold;
  margin-bottom: 5px;
}

.artifact-content, .history-content {
  white-space: pre-wrap;
  font-family: monospace;
  font-size: 12px;
}

.agent-loading {
  display: flex;
  align-items: center;
  margin-top: 8px;
  padding: 8px;
  background-color: #e8f5e9;
  border-radius: 4px;
  color: #388e3c;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  margin-right: 8px;
  border: 2px solid #388e3c;
  border-radius: 50%;
  border-top-color: transparent;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.ws-test-actions {
  display: flex;
  align-items: center;
}
</style> 