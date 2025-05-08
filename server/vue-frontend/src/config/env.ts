// 环境配置文件
interface EnvConfig {
  apiBaseUrl: string;
}

// 获取当前环境
function getEnvironment(): string {
  // NODE_ENV 用于区分开发/生产环境
  const env = process.env.NODE_ENV || 'development';
  
  // 检查是否在localhost环境中
  const isLocalhost = typeof window !== 'undefined' && 
                      (window.location.hostname === 'localhost' || 
                       window.location.hostname === '127.0.0.1');
  
  // 检查是否在Vercel环境中
  const isVercel = process.env.VERCEL === 'true' || 
                  (typeof window !== 'undefined' && 
                   window.location.hostname.includes('vercel.app'));
  
  if (isLocalhost) {
    return 'localhost';
  } else if (isVercel) {
    return 'vercel';
  }
  
  return env;
}

// 动态获取API基础URL
function getApiBaseUrl(): string {
  const hostname = typeof window !== 'undefined' ? window.location.hostname : '';
  const protocol = typeof window !== 'undefined' ? window.location.protocol : 'https:';
  
  // 如果是localhost环境，直接连接本地API端口
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return '/api';
  }
  
  // 其他环境（生产或vercel等），使用当前域名+/beapi路径
  return `${protocol}//${hostname}/beapi`;
}

// 不同环境的配置
const configs: Record<string, EnvConfig> = {
  development: {
    apiBaseUrl: getApiBaseUrl()
  },
  localhost: {
    apiBaseUrl: '/api'
  },
  production: {
    apiBaseUrl: getApiBaseUrl()
  },
  vercel: {
    // Vercel环境使用环境变量中配置的API URL或默认值
    apiBaseUrl: process.env.VUE_APP_API_URL || getApiBaseUrl()
  }
};

// 导出当前环境的配置
export const config = configs[getEnvironment()] || configs.development;

// 导出一个函数用于在运行时动态设置API URL
export function setApiBaseUrl(url: string): void {
  if (url && url.trim() !== '') {
    if (getEnvironment() === 'localhost') {
      configs.localhost.apiBaseUrl = url;
    } else {
      configs[getEnvironment()].apiBaseUrl = url;
    }
    (config as EnvConfig).apiBaseUrl = url;
  }
}

console.log('API Base URL:', config.apiBaseUrl);

export default config; 