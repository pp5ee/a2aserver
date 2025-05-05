import axios from 'axios';
import { getWalletAddress, getSignatureInfo, refreshSignatureIfNeeded, connectAndSign, isWalletConnected } from './solana-wallet';

// 扩展Window接口以支持动态属性
declare global {
  interface Window {
    [key: string]: any;
  }
}

// 根据环境决定是否使用代理
const useProxy = process.env.NODE_ENV === 'development';
const baseURL = useProxy ? '/api' : 'http://localhost:12000';

// 创建axios实例
const api = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  },
  // 不要发送凭证，这可能导致预检请求
  withCredentials: false
});

// 定义API接口路径 - 所有这些接口都需要签名
const API_PATHS = [
  '/conversation/create',
  '/conversation/delete',
  '/message/send', 
  '/agent/register',
  '/conversation/list',
  '/message/list',
  '/task/list',
  '/agent/list',
  '/events/get'
];

// 检查请求路径是否需要签名
function requiresSignature(url: string): boolean {
  // 根据需求修改，所有API路径都需要签名
  return API_PATHS.some(path => url.includes(path));
}

// 请求拦截器
api.interceptors.request.use(
  async config => {
    // 为所有请求添加时间戳，避免缓存
    if (config.method === 'post' || config.method === 'get') {
      if (!config.params) {
        config.params = {};
      }
      config.params._t = new Date().getTime();
    }
    
    // 检查是否是API请求 - 现在所有API都需要签名
    const isApiRequest = requiresSignature(config.url || '');
    
    // 如果是API请求，确保有钱包地址和签名
    if (isApiRequest) {
      // 获取钱包地址
      const walletAddress = getWalletAddress();
      
      // 检查钱包是否已连接，如果未连接则返回错误
      if (!walletAddress) {
        console.log('API请求需要钱包连接，但钱包未连接');
        // 触发钱包错误事件
        const event = new CustomEvent('wallet-error', {
          detail: { message: '请求需要连接钱包，请点击"连接钱包"按钮' }
        });
        window.dispatchEvent(event);
        throw new Error('请求需要连接钱包');
      }
      
      // 添加钱包地址到请求头
      config.headers['X-Solana-PublicKey'] = walletAddress;
      
      // 获取签名信息并添加到请求头
      const signatureInfo = getSignatureInfo();
      if (signatureInfo) {
        config.headers['X-Solana-Nonce'] = signatureInfo.nonce;
        config.headers['X-Solana-Signature'] = signatureInfo.signature;
        
        // 记录请求头信息（仅开发环境）
        if (process.env.NODE_ENV === 'development') {
          console.log('请求头包含签名信息:', {
            publicKey: walletAddress.substring(0, 6) + '...' + walletAddress.substring(walletAddress.length - 4),
            nonce: signatureInfo.nonce,
            signature: signatureInfo.signature.substring(0, 10) + '...'
          });
        }
      } else {
        // 如果没有有效签名，返回错误提示用户手动签名
        console.warn('未找到有效签名信息，需要用户手动签名');
        // 触发签名错误事件
        const event = new CustomEvent('signature-error', {
          detail: { message: '请求需要有效签名，请点击"需要签名"按钮进行签名' }
        });
        window.dispatchEvent(event);
        throw new Error('需要有效签名才能继续请求');
      }
      
      if (process.env.NODE_ENV === 'development') {
        console.log(`使用钱包地址 ${walletAddress.substring(0, 6)}...${walletAddress.substring(walletAddress.length - 4)} 发送请求`);
      }
    } else {
      // 非API请求，不需要签名
      console.log('非API请求，无需钱包签名:', config.url);
    }
    
    console.log('正在发送请求:', config.url, config.method);
    return config;
  },
  error => {
    console.error('请求错误:', error);
    return Promise.reject(error);
  }
);

// 响应拦截器
api.interceptors.response.use(
  response => {
    console.log('收到响应:', response.config.url);
    return response;
  },
  error => {
    // 详细记录错误信息
    if (error.response) {
      console.error('API请求错误:', error.response.status, error.response.data);
      
      // 钱包或签名相关错误处理
      if (error.response.status === 401 && error.response.data && error.response.data.error) {
        const errorMsg = error.response.data.error;
        
        // 如果错误与签名相关
        if (errorMsg.includes('签名')) {
          // 触发签名错误事件
          const event = new CustomEvent('signature-error', {
            detail: { message: errorMsg }
          });
          window.dispatchEvent(event);
        } 
        // 如果错误与钱包相关
        else if (errorMsg.includes('钱包')) {
          // 触发钱包错误事件
          const event = new CustomEvent('wallet-error', {
            detail: { message: errorMsg }
          });
          window.dispatchEvent(event);
        }
      }
    } else if (error.request) {
      console.error('未收到响应:', error.request);
    } else {
      console.error('请求配置错误:', error.message);
    }
    return Promise.reject(error);
  }
);

// API方法
export const apiService = {
  // 对话相关
  async createConversation() {
    return api.post('/conversation/create', {});
  },
  
  async listConversations() {
    return api.post('/conversation/list', {});
  },
  
  async deleteConversation(conversationId: string) {
    return api.post('/conversation/delete', { conversation_id: conversationId });
  },
  
  async sendMessage(params: any) {
    return api.post('/message/send', { params });
  },
  
  async listMessages(conversationId: string) {
    return api.post('/message/list', { params: conversationId });
  },
  
  // 任务相关
  async listTasks() {
    return api.post('/task/list', {});
  },
  
  // 代理相关
  async registerAgent(url: string) {
    try {
      console.log('注册代理:', url);
      // 修复参数格式，直接传递URL字符串而不是对象
      return await api.post('/agent/register', { params: url });
    } catch (error) {
      console.error('注册代理失败:', error);
      throw error;
    }
  },
  
  async listAgents() {
    return api.post('/agent/list', {});
  },
  
  // 事件相关
  async getEvents() {
    return api.post('/events/get', {});
  },
  
  // API密钥相关
  async updateApiKey(apiKey: string) {
    return api.post('/api_key/update', { api_key: apiKey });
  },
  
  // 钱包相关
  async checkWalletConnection() {
    const walletAddress = getWalletAddress();
    return { 
      connected: !!walletAddress,
      address: walletAddress
    };
  }
};

export default api; 