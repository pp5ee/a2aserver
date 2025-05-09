import { createStore } from 'vuex'
import { apiService } from '../services/api'
import { v4 as uuidv4 } from 'uuid'

// 类型定义
export interface ContentPart {
  content: string | Record<string, any>;
  mediaType: string;
}

export interface StateMessage {
  messageId: string;
  role: string;
  content: ContentPart[];
}

export interface StateConversation {
  conversationId: string;
  conversationName: string;
  isActive: boolean;
  messageIds: string[];
}

export interface StateTask {
  taskId: string;
  sessionId: string | null;
  state: string | null;
  message: StateMessage;
  artifacts: ContentPart[][];
}

export interface SessionTask {
  sessionId: string;
  task: StateTask;
}

export interface StateEvent {
  conversationId: string;
  actor: string;
  role: string;
  id: string;
  content: ContentPart[];
}

export interface RootState {
  sidenavOpen: boolean;
  themeMode: 'system' | 'light' | 'dark';
  currentConversationId: string;
  conversations: StateConversation[];
  messages: StateMessage[];
  taskList: SessionTask[];
  backgroundTasks: Record<string, string>;
  messageAliases: Record<string, string>;
  completedForms: Record<string, Record<string, any> | null>;
  formResponses: Record<string, string>;
  pollingInterval: number;
  apiKey: string;
  usesVertexAi: boolean;
  apiKeyDialogOpen: boolean;
  isPolling: boolean;
}

export default createStore<RootState>({
  state: {
    sidenavOpen: false,
    themeMode: 'system',
    currentConversationId: '',
    conversations: [],
    messages: [],
    taskList: [],
    backgroundTasks: {},
    messageAliases: {},
    completedForms: {},
    formResponses: {},
    pollingInterval: 5,
    apiKey: '',
    usesVertexAi: false,
    apiKeyDialogOpen: false,
    isPolling: false
  },
  getters: {
    getCurrentConversation(state) {
      return state.conversations.find(c => c.conversationId === state.currentConversationId);
    },
    // 检查消息是否正在处理中
    isProcessing: (state) => (messageId: string) => {
      return Object.values(state.messageAliases).includes(messageId);
    },
    // 获取处理状态文本
    getProcessingText: () => (messageId: string) => {
      return '处理中...';
    }
  },
  mutations: {
    setConversations(state, conversations: StateConversation[]) {
      state.conversations = conversations;
    },
    setMessages(state, messages: StateMessage[]) {
      state.messages = messages;
    },
    setCurrentConversationId(state, id: string) {
      state.currentConversationId = id;
    },
    setTaskList(state, taskList: SessionTask[]) {
      state.taskList = taskList;
    },
    setBackgroundTasks(state, tasks: Record<string, string>) {
      state.backgroundTasks = tasks;
    },
    toggleSidenav(state) {
      state.sidenavOpen = !state.sidenavOpen;
    },
    setThemeMode(state, mode: 'system' | 'light' | 'dark') {
      state.themeMode = mode;
    },
    setApiKey(state, key: string) {
      state.apiKey = key;
    },
    setUsesVertexAi(state, uses: boolean) {
      state.usesVertexAi = uses;
    },
    setApiKeyDialogOpen(state, open: boolean) {
      state.apiKeyDialogOpen = open;
    },
    setIsPolling(state, isPolling: boolean) {
      state.isPolling = isPolling;
    },
    setPollingInterval(state, interval: number) {
      state.pollingInterval = interval;
    },
    addBackgroundTask(state, { messageId, text }: { messageId: string, text: string }) {
      state.backgroundTasks = { ...state.backgroundTasks, [messageId]: text };
    },
    addMessage(state, message: StateMessage) {
      state.messages.push(message);
    }
  },
  actions: {
    async fetchConversations({ commit }) {
      try {
        const response = await apiService.listConversations();
        const conversations = response.data.result.map((conv: any) => ({
          conversationId: conv.conversation_id,
          conversationName: conv.name || '',
          isActive: conv.is_active,
          messageIds: Array.isArray(conv.messages) 
            ? conv.messages.map((m: any) => m.metadata?.message_id || '') 
            : []
        }));
        commit('setConversations', conversations);
      } catch (error) {
        console.error('获取对话列表失败:', error);
      }
    },
    async fetchMessages({ commit, state }) {
      if (!state.currentConversationId) return;
      
      try {
        const response = await apiService.listMessages(state.currentConversationId);
        
        const messages = response.data.result.map((msg: any) => ({
          messageId: msg.metadata?.message_id || '',
          role: msg.role,
          content: msg.parts.map((part: any) => {
            if (part.type === 'text') {
              return {
                content: part.text,
                mediaType: 'text/plain'
              };
            } else if (part.type === 'file') {
              return {
                content: part.file.uri || part.file.bytes,
                mediaType: part.file.mimeType
              };
            } else if (part.type === 'data') {
              return {
                content: part.data,
                mediaType: 'application/json'
              };
            }
            return {
              content: '',
              mediaType: 'text/plain'
            };
          })
        }));
        
        commit('setMessages', messages);
      } catch (error) {
        console.error('获取消息失败:', error);
      }
    },
    async createConversation({ commit }) {
      try {
        const response = await apiService.createConversation();
        
        // 检查是否有错误信息
        if (response.data && response.data.error) {
          console.error('创建对话失败:', response.data.error);
          return { error: response.data.error };
        }
        
        const conversationId = response.data.result.conversation_id;
        commit('setCurrentConversationId', conversationId);
        commit('setMessages', []);
        return conversationId;
      } catch (error) {
        console.error('创建对话失败:', error);
        return { error: '创建对话时发生错误，请稍后再试' };
      }
    },
    async sendMessage({ commit, state }, { content, messageId }) {
      try {
        // 添加为后台任务
        commit('addBackgroundTask', { messageId, text: '' });
        
        // 添加到消息列表
        const userMessage = {
          messageId,
          role: 'user',
          content: [{
            content,
            mediaType: 'text/plain'
          }]
        };
        commit('addMessage', userMessage);
        
        // 发送消息到服务器
        await apiService.sendMessage({
          role: 'user',
          parts: [{ type: 'text', text: content }],
          metadata: {
            conversation_id: state.currentConversationId,
            message_id: messageId
          }
        });
        
        // 更新消息列表
        this.dispatch('fetchMessages');
      } catch (error) {
        console.error('发送消息失败:', error);
      }
    },
    async pollUpdates({ commit, state, dispatch }) {
      if (state.isPolling) return;
      
      commit('setIsPolling', true);
      
      try {
        // 不再自动获取会话列表，仅在当前有会话时获取消息和任务
        if (state.currentConversationId) {
          await dispatch('fetchMessages');
        }
        
        // 获取任务列表
        const taskResponse = await apiService.listTasks();
        if (taskResponse.data && taskResponse.data.result) {
          const tasks = taskResponse.data.result.map((task: any) => ({
            sessionId: task.sessionId,
            task: {
              taskId: task.id,
              sessionId: task.sessionId,
              state: task.status.state,
              message: {
                messageId: task.status.message?.metadata?.message_id || '',
                role: task.status.message?.role || '',
                content: (task.status.message?.parts || []).map((part: any) => ({
                  content: part.type === 'text' ? part.text : 
                          part.type === 'file' ? part.file.uri || part.file.bytes : 
                          part.type === 'data' ? part.data : '',
                  mediaType: part.type === 'text' ? 'text/plain' : 
                            part.type === 'file' ? part.file.mimeType : 
                            'application/json'
                }))
              },
              artifacts: (task.artifacts || []).map((artifact: any) => (
                (artifact.parts || []).map((part: any) => ({
                  content: part.type === 'text' ? part.text : 
                          part.type === 'file' ? part.file.uri || part.file.bytes : 
                          part.type === 'data' ? part.data : '',
                  mediaType: part.type === 'text' ? 'text/plain' : 
                            part.type === 'file' ? part.file.mimeType : 
                            'application/json'
                }))
              ))
            }
          }));
          commit('setTaskList', tasks);
        }
      } catch (error) {
        console.error('轮询更新失败:', error);
      } finally {
        commit('setIsPolling', false);
      }
    },
    async updateApiKey({ commit }, apiKey) {
      try {
        await apiService.updateApiKey(apiKey);
        commit('setApiKey', apiKey);
        commit('setApiKeyDialogOpen', false);
      } catch (error) {
        console.error('更新API密钥失败:', error);
      }
    }
  },
  modules: {
  }
}) 