<template>
  <div class="agents-view">
    <div class="content-container">
      <div class="header">
        <h1>代理管理</h1>
        <div class="icon">
          <i class="material-icons">supervisor_account</i>
        </div>
      </div>
      
      <div class="agents-section">
        <h2>已连接代理</h2>
        
        <!-- 已注册代理列表 -->
        <div class="agent-list" v-if="agents.length > 0">
          <div class="agent-card" v-for="(agent, index) in agents" :key="index">
            <div class="agent-header">
              <div class="agent-name">{{ agent.name }}</div>
              <div class="agent-status">
                <span class="status-badge" :class="{'active': agent.is_online === 'yes'}">
                  {{ agent.is_online === 'yes' ? '在线' : '离线' }}
                </span>
              </div>
            </div>
            <div class="agent-details">
              <div class="agent-info-item">
                <span class="info-label">URL:</span>
                <span class="info-value">{{ agent.url }}</span>
              </div>
              <div class="agent-info-item" v-if="agent.description">
                <span class="info-label">描述:</span>
                <span class="info-value">{{ agent.description }}</span>
              </div>
              <div class="agent-info-item" v-if="agent.expire_at">
                <span class="info-label">过期时间:</span>
                <span class="info-value">{{ formatExpireDate(agent.expire_at) }}</span>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 无代理提示 -->
        <div v-else class="no-agents">
          <div class="empty-state">
            <i class="material-icons">extension_off</i>
            <p>暂无已连接代理</p>
          </div>
        </div>
        
        <!-- 刷新按钮 -->
        <div class="refresh-container">
          <button class="refresh-button" @click="loadAgents">
            <i class="material-icons">refresh</i> 刷新列表
          </button>
        </div>
      </div>
    </div>
    
    <!-- 提示信息 -->
    <div class="toast" v-if="toast.show">
      <div class="toast-content" :class="toast.type">
        {{ toast.message }}
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, onMounted } from 'vue';
import { apiService } from '../services/api';

// 定义代理信息接口
interface AgentInfo {
  name: string;
  url: string;
  description?: string;
  is_active?: boolean;
  is_online?: string;  // 'yes', 'no', 'unknown'
  expire_at?: string;
  nft_mint_id?: string;
}

// 定义提示信息接口
interface ToastState {
  show: boolean;
  message: string;
  type: 'success' | 'error';
}

export default defineComponent({
  name: 'AgentsView',
  
  setup() {
    // 代理列表
    const agents = ref<AgentInfo[]>([]);
    
    // 提示信息
    const toast = reactive<ToastState>({
      show: false,
      message: '',
      type: 'success'
    });
    
    // 显示提示
    const showToast = (message: string, type: 'success' | 'error' = 'success') => {
      toast.message = message;
      toast.type = type;
      toast.show = true;
      
      // 3秒后自动关闭
      setTimeout(() => {
        toast.show = false;
      }, 3000);
    };
    
    // 加载代理列表
    const loadAgents = async () => {
      try {
        const response = await apiService.listAgents();
        if (response.data && response.data.result) {
          agents.value = response.data.result;
          if (agents.value.length > 0) {
            showToast(`已加载 ${agents.value.length} 个代理`, 'success');
          }
        }
      } catch (error) {
        console.error('加载代理列表失败:', error);
        showToast('加载代理列表失败', 'error');
      }
    };
    
    // 格式化过期日期
    const formatExpireDate = (dateString?: string) => {
      if (!dateString) return '未知';
      try {
        const date = new Date(dateString);
        return date.toLocaleString('zh-CN', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit'
        });
      } catch (error) {
        console.error('日期格式化错误:', error);
        return dateString;
      }
    };
    
    // 挂载时加载代理列表
    onMounted(() => {
      loadAgents();
    });
    
    return {
      agents,
      toast,
      loadAgents,
      formatExpireDate
    };
  }
});
</script>

<style scoped>
.agents-view {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.content-container {
  background-color: #f8f9fa;
  border-radius: 10px;
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2rem;
  border-bottom: 1px solid #e1e4e8;
  padding-bottom: 1rem;
}

.header h1 {
  font-size: 1.8rem;
  color: #253858;
  margin: 0;
}

.header .icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #0052cc;
  border-radius: 50%;
}

.header .icon i {
  color: white;
  font-size: 24px;
}

.agents-section {
  margin-bottom: 2rem;
}

.agents-section h2 {
  font-size: 1.4rem;
  color: #253858;
  margin-bottom: 1rem;
}

.agent-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.agent-card {
  background-color: white;
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: transform 0.2s, box-shadow 0.2s;
}

.agent-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.agent-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.8rem;
  padding-bottom: 0.8rem;
  border-bottom: 1px solid #eaecef;
}

.agent-name {
  font-weight: 600;
  font-size: 1.1rem;
  color: #172b4d;
}

.status-badge {
  font-size: 0.8rem;
  padding: 0.2rem 0.6rem;
  border-radius: 12px;
  background-color: #ebecf0;
  color: #6b778c;
}

.status-badge.active {
  background-color: #e3fcef;
  color: #006644;
}

.status-badge:not(.active) {
  background-color: #ffebe6;
  color: #bf2600;
}

.agent-details {
  font-size: 0.9rem;
}

.agent-info-item {
  margin-bottom: 0.5rem;
  display: flex;
  flex-direction: column;
}

.info-label {
  font-weight: 500;
  color: #6b778c;
  margin-bottom: 0.2rem;
}

.info-value {
  color: #172b4d;
  word-break: break-all;
}

.no-agents {
  display: flex;
  justify-content: center;
  padding: 3rem 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  color: #6b778c;
}

.empty-state i {
  font-size: 48px;
  margin-bottom: 1rem;
  color: #dfe1e6;
}

.refresh-container {
  display: flex;
  justify-content: center;
  margin-top: 1.5rem;
}

.refresh-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background-color: #f4f5f7;
  color: #0052cc;
  border: none;
  padding: 0.6rem 1.2rem;
  border-radius: 3px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.2s;
}

.refresh-button:hover {
  background-color: #ebecf0;
}

.toast {
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  z-index: 1000;
}

.toast-content {
  padding: 0.8rem 1.5rem;
  border-radius: 4px;
  color: white;
  font-size: 0.9rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.toast-content.success {
  background-color: #00875a;
}

.toast-content.error {
  background-color: #de350b;
}
</style> 