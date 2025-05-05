// 环境配置文件
interface EnvConfig {
  apiBaseUrl: string;
}

// 获取当前环境
function getEnvironment(): string {
  // NODE_ENV 用于区分开发/生产环境
  const env = process.env.NODE_ENV || 'development';
  
  // 检查是否在Vercel环境中
  const isVercel = process.env.VERCEL === 'true' || window.location.hostname.includes('vercel.app');
  
  if (isVercel) {
    return 'vercel';
  }
  
  return env;
}

// 不同环境的配置
const configs: Record<string, EnvConfig> = {
  development: {
    apiBaseUrl: '/api' // 开发环境使用代理
  },
  production: {
    apiBaseUrl: 'http://localhost:12000' // 默认生产环境指向本地API
  },
  vercel: {
    // Vercel环境使用环境变量中配置的API URL或默认值
    // 这个URL将通过Vercel环境变量设置
    apiBaseUrl: process.env.VUE_APP_API_URL || 'https://your-api-domain.com'
  }
};

// 导出当前环境的配置
export const config = configs[getEnvironment()] || configs.development;

// 导出一个函数用于在运行时动态设置API URL
export function setApiBaseUrl(url: string): void {
  if (url && url.trim() !== '') {
    configs.vercel.apiBaseUrl = url;
    // 如果当前环境是vercel，更新当前配置
    if (getEnvironment() === 'vercel') {
      (config as EnvConfig).apiBaseUrl = url;
    }
  }
}

export default config; 