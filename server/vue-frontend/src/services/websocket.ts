import { config } from '../config/env';
import { getWalletAddress, getSignatureInfo, refreshSignatureIfNeeded } from './solana-wallet';

// WebSocket消息类型
export interface WebSocketMessage {
  type: string;
  [key: string]: any;
}

// 新消息类型
export interface NewMessageEvent {
  type: 'new_message';
  conversation_id: string;
  message: {
    id: string;
    role: string;
    content: Array<{
      type: string;
      text: string | null;
    }>;
  };
}

// 任务更新类型
export interface TaskUpdateEvent {
  type: 'task_update';
  conversation_id: string;
  message_id?: string;
  task: {
    id: string;
    sessionId: string;
    status: {
      state: string;
      message: string;
      timestamp: string;
    };
    history?: Array<{
      role: string;
      parts: Array<{
        type: string;
        text: string | null;
      }>;
    }>;
    artifacts?: Array<{
      name: string;
      parts: Array<{
        type: string;
        text: string | null;
      }>;
    }>;
  };
}

// WebSocket服务类
class WebSocketService {
  private socket: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectTimeout: number | null = null;
  private pingInterval: number | null = null;
  private listeners: { [key: string]: Array<(data: any) => void> } = {};
  private connectionPromise: Promise<WebSocket> | null = null;
  private connectionResolve: ((socket: WebSocket) => void) | null = null;
  private connectionReject: ((reason: any) => void) | null = null;

  // 获取WebSocket URL
  private getWebSocketUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const hostname = window.location.hostname;
    
    // 如果是localhost环境，直接使用12000端口（后端服务器端口）
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return `${protocol}//${hostname}:12000/api/ws`;
    }
    
    // 非本地环境，使用当前域名
    const host = window.location.host;
    return `${protocol}//${host}/api/ws`;
  }

  // 连接WebSocket
  public connect(): Promise<WebSocket> {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      console.log('WebSocket已连接，直接返回现有连接');
      return Promise.resolve(this.socket);
    }

    if (this.connectionPromise) {
      console.log('WebSocket连接已在进行中，等待连接完成');
      return this.connectionPromise;
    }

    console.log('开始建立新的WebSocket连接');
    this.connectionPromise = new Promise<WebSocket>((resolve, reject) => {
      this.connectionResolve = resolve;
      this.connectionReject = reject;

      // 获取钱包地址和签名信息
      const walletAddress = getWalletAddress();
      if (!walletAddress) {
        console.error('无法连接WebSocket：未找到钱包地址');
        reject(new Error('No wallet address available'));
        this.connectionPromise = null;
        return;
      }

      // 获取签名信息
      const signatureInfo = getSignatureInfo();
      if (!signatureInfo) {
        console.log('未找到签名信息，尝试刷新签名');
        refreshSignatureIfNeeded()
          .then(() => {
            // 触发重新连接
            this.disconnect();
            this.connectionPromise = null;
            this.connect().then(resolve).catch(reject);
          })
          .catch(error => {
            console.error('刷新签名失败:', error);
            reject(new Error('Failed to get signature: ' + error.message));
            this.connectionPromise = null;
          });
        return;
      }

      // 构建包含鉴权信息的WebSocket URL
      const baseUrl = this.getWebSocketUrl();
      
      try {
        // 使用URL参数传递鉴权信息，更可靠
        const authUrl = `${baseUrl}?publicKey=${encodeURIComponent(walletAddress)}&nonce=${encodeURIComponent(signatureInfo.nonce)}&signature=${encodeURIComponent(signatureInfo.signature)}`;
        
        console.log(`连接WebSocket，URL: ${baseUrl} (包含认证参数)，钱包地址: ${walletAddress.substring(0, 6)}...`);
        
        // 在创建新连接前关闭任何现有连接
        if (this.socket) {
          console.log('关闭现有WebSocket连接');
          this.socket.close();
          this.socket = null;
        }
        
        this.socket = new WebSocket(authUrl);
        
        this.socket.onopen = () => {
          console.log('WebSocket连接已建立');
          this.reconnectAttempts = 0;

          // 设置心跳检测
          this.startPingInterval();

          if (this.connectionResolve && this.socket) {
            this.connectionResolve(this.socket);
            this.connectionResolve = null;
          }
        };

        this.socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            // 处理不同类型的消息
            if (data.type) {
              // 增加消息接收详细日志
              if (data.type === 'new_message') {
                console.log(`收到新消息: ID=${data.message?.id}, 角色=${data.message?.role}, 会话=${data.conversation_id}`);
                // 确保消息内容存在
                if (!data.message?.content || data.message.content.length === 0) {
                  console.warn('收到的消息没有内容:', data);
                }
              } else if (data.type === 'task_update') {
                console.log(`收到任务更新: ID=${data.task?.id}, 状态=${data.task?.status?.state}, 会话=${data.conversation_id}`);
              } else if (data.type === 'connection_established') {
                console.log(`WebSocket连接已确认: 钱包=${data.wallet_address}`);
              } else if (data.type === 'pong') {
                console.log('收到pong响应:', data.timestamp);
              } else {
                console.log(`收到${data.type}类型消息:`, data);
              }
              
              // 触发事件
              this.emitEvent(data.type, data);
            } else {
              console.warn('接收到未知类型的WebSocket消息:', data);
            }
          } catch (error) {
            console.error('解析WebSocket消息出错:', error);
            console.error('原始消息内容:', event.data);
          }
        };

        this.socket.onclose = (event) => {
          console.log(`WebSocket连接已关闭: 代码=${event.code}, 原因="${event.reason}"`);
          this.clearPingInterval();

          const currentSocket = this.socket;
          this.socket = null;

          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.attemptReconnect();
          } else {
            console.error(`已达到最大重连尝试次数 (${this.maxReconnectAttempts}次)`);
            if (this.connectionReject) {
              this.connectionReject(new Error('Maximum reconnection attempts reached'));
              this.connectionReject = null;
            }
          }
        };

        this.socket.onerror = (error) => {
          console.error('WebSocket连接错误:', error);
          if (this.connectionReject) {
            this.connectionReject(error);
            this.connectionReject = null;
          }
        };
      } catch (error) {
        console.error('创建WebSocket连接失败:', error);
        if (this.connectionReject) {
          this.connectionReject(error);
          this.connectionReject = null;
        }
        this.connectionPromise = null;
      }
    });

    // 添加finally处理，确保在Promise完成后重置状态
    const finalPromise = this.connectionPromise.finally(() => {
      this.connectionPromise = null;
      this.connectionResolve = null;
      this.connectionReject = null;
    });

    return finalPromise;
  }

  // 断开WebSocket连接
  public disconnect(): void {
    this.clearPingInterval();
    
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }

  // 发送消息
  public send(message: any): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      console.error('WebSocket is not connected');
      return;
    }

    try {
      this.socket.send(JSON.stringify(message));
    } catch (error) {
      console.error('Error sending WebSocket message:', error);
    }
  }

  // 发送ping消息
  private sendPing(): void {
    this.send({
      type: 'ping',
      timestamp: new Date().toISOString()
    });
  }

  // 设置ping间隔
  private startPingInterval(): void {
    this.clearPingInterval();
    this.pingInterval = window.setInterval(() => {
      this.sendPing();
    }, 30000); // 每30秒发送一次ping
  }

  // 清除ping间隔
  private clearPingInterval(): void {
    if (this.pingInterval !== null) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  // 尝试重连
  private attemptReconnect(): void {
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    
    console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`);
    
    if (this.reconnectTimeout !== null) {
      clearTimeout(this.reconnectTimeout);
    }
    
    this.reconnectTimeout = window.setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect().catch(error => {
        console.error('Reconnection failed:', error);
      });
    }, delay);
  }

  // 添加事件监听器
  public on<T>(event: string, callback: (data: T) => void): void {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback as (data: any) => void);
  }

  // 移除事件监听器
  public off(event: string, callback?: (data: any) => void): void {
    if (!this.listeners[event]) {
      return;
    }

    if (!callback) {
      delete this.listeners[event];
    } else {
      this.listeners[event] = this.listeners[event].filter(
        listener => listener !== callback
      );
    }
  }

  // 触发事件
  private emitEvent(event: string, data: any): void {
    if (this.listeners[event]) {
      this.listeners[event].forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`Error in WebSocket ${event} event handler:`, error);
        }
      });
    }
  }
}

// 创建单例实例
export const webSocketService = new WebSocketService();

export default webSocketService; 