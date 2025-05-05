/**
 * Solana钱包工具
 * 提供与Solana钱包交互的功能，包括连接钱包、签名等
 */

// 存储在localStorage中的key
const WALLET_KEY = 'phantomWallet';

// 用于调试的模拟钱包地址
const DEBUG_WALLET_ADDRESS = 'DEBUG_' + Math.random().toString(36).substring(2, 15);

// 预设的过期时间（毫秒）
export const EXPIRY_PRESETS = {
  DAY_7: 7 * 24 * 60 * 60 * 1000,
  DAY_30: 30 * 24 * 60 * 60 * 1000,
  DAY_90: 90 * 24 * 60 * 60 * 1000
};

/**
 * 计算未来的时间戳（毫秒）
 * @param duration 持续时间（毫秒）
 * @returns 未来的时间戳
 */
function getFutureTimestamp(duration: number): number {
  return Date.now() + duration;
}

/**
 * 格式化日期时间为字符串
 * @param timestamp 时间戳
 * @returns 格式化后的日期字符串
 */
function formatDateTime(timestamp: number): string {
  const date = new Date(timestamp);
  return date.toLocaleString();
}

/**
 * 检查钱包是否已连接
 * @returns 返回钱包是否已连接
 */
export function isWalletConnected(): boolean {
  const walletData = localStorage.getItem(WALLET_KEY);
  return !!walletData;
}

/**
 * 获取钱包地址
 * @returns 钱包地址或null
 */
export function getWalletAddress(): string | null {
  try {
    const walletData = localStorage.getItem(WALLET_KEY);
    if (walletData) {
      const wallet = JSON.parse(walletData);
      return wallet.address;
    }
  } catch (error) {
    console.error('获取钱包地址失败:', error);
  }
  return null;
}

/**
 * 获取签名信息
 * @returns 签名信息对象，包含nonce和signature
 */
export function getSignatureInfo(): { nonce: string; signature: string } | null {
  try {
    const walletData = localStorage.getItem(WALLET_KEY);
    if (walletData) {
      const wallet = JSON.parse(walletData);
      if (wallet.nonce && wallet.signature) {
        return {
          nonce: wallet.nonce,
          signature: wallet.signature
        };
      }
    }
  } catch (error) {
    console.error('获取签名信息失败:', error);
  }
  return null;
}

/**
 * 检查签名是否过期
 * @returns 是否需要重新签名
 */
export function isSignatureExpired(): boolean {
  try {
    const signInfo = getSignatureInfo();
    if (!signInfo) return true;
    
    const nonce = parseInt(signInfo.nonce, 10);
    return Date.now() >= nonce;
  } catch (error) {
    console.error('检查签名是否过期失败:', error);
    return true;
  }
}

/**
 * 获取签名过期时间
 * @returns 过期时间戳或null
 */
export function getSignatureExpiryTime(): number | null {
  try {
    const signInfo = getSignatureInfo();
    if (!signInfo) return null;
    
    return parseInt(signInfo.nonce, 10);
  } catch (error) {
    console.error('获取签名过期时间失败:', error);
    return null;
  }
}

/**
 * 连接钱包并签名
 * @param expiryDuration 签名过期时间（毫秒），默认7天
 * @returns 连接结果
 */
export async function connectAndSign(expiryDuration: number | string = EXPIRY_PRESETS.DAY_7): Promise<{ 
  success: boolean; 
  address?: string;
  nonce?: string;
  signature?: string;
  error?: string;
}> {
  try {
    console.log('开始连接钱包...');
    
    // 增强钱包检测逻辑
    let phantomProvider = null;
    let hasPhantom = false;
    
    // 检查方法1：直接通过window对象检测
    if (window['phantom']?.solana?.isPhantom) {
      console.log('方法1：通过window.phantom检测到Phantom钱包');
      phantomProvider = window['phantom'].solana;
      hasPhantom = true;
    }
    // 检查方法2：通过window.solana检测
    else if (window['solana']?.isPhantom) {
      console.log('方法2：通过window.solana检测到Phantom钱包');
      phantomProvider = window['solana'];
      hasPhantom = true;
    }
    // 检查方法3：通过solanaWeb3检测（如果有的话）
    else if (window['solanaWeb3']) {
      console.log('方法3：通过window.solanaWeb3检测到Solana Web3');
      phantomProvider = window['solanaWeb3'];
      hasPhantom = true;
    }
    // 检查方法4：通过浏览器扩展API直接检测
    else {
      try {
        console.log('方法4：尝试列出浏览器扩展...');
        if (navigator && navigator.userAgent.indexOf('Chrome') > -1) {
          console.log('Chrome环境，请确保钱包扩展已启用并允许访问内网站点');
          console.log('提示：可以尝试在Chrome扩展设置中允许"在隐身模式下"和"允许访问文件网址"');
        }
      } catch (extError) {
        console.warn('检测浏览器扩展出错:', extError);
      }
    }
    
    let address: string;
    let signature: string;
    
    // 确保expiryDuration是数字
    const actualExpiry = typeof expiryDuration === 'string' ? 
      EXPIRY_PRESETS.DAY_7 : // 如果是字符串，使用默认值
      expiryDuration;
    
    // 生成指定过期时间的时间戳作为nonce
    const nonce = getFutureTimestamp(actualExpiry).toString();
    const expiryDate = formatDateTime(parseInt(nonce));
    
    console.log(`设置签名有效期至: ${expiryDate}（${Math.round(actualExpiry / (24 * 60 * 60 * 1000))}天）`);
    
    if (!hasPhantom || !phantomProvider) {
      console.warn('未检测到Phantom钱包，使用调试模式');
      console.warn('在内网环境中，请确保：');
      console.warn('1. Phantom钱包扩展已安装并启用');
      console.warn('2. 浏览器允许扩展在内网站点上运行');
      console.warn('3. 如果使用的是HTTP协议，尝试使用HTTPS');
      
      // 如果在内网环境中，提供调试方式解决
      if (window.location.hostname === 'localhost' || 
          window.location.hostname.includes('192.168.') || 
          window.location.hostname.includes('10.') || 
          window.location.hostname.includes('172.')) {
        console.log('检测到内网环境，提供临时解决方案');
        console.log('您可以：');
        console.log('1. 在Chrome浏览器中访问 chrome://extensions');
        console.log('2. 找到Phantom钱包扩展，开启"允许访问文件网址"选项');
        console.log('3. 在扩展详情中，确保"网站访问权限"设置为"在所有网站上"');
      }
      
      // 调试模式：生成模拟签名和地址
      address = DEBUG_WALLET_ADDRESS;
      signature = 'DEBUG_SIGNATURE_' + Math.random().toString(36).substring(2, 15);
      
      await new Promise(resolve => setTimeout(resolve, 500)); // 模拟延迟
    } else {
      console.log('检测到Phantom钱包，开始连接...');
      
      try {
        // 连接到Phantom钱包
        const resp = await phantomProvider.connect();
        address = resp.publicKey.toString();
        
        // 直接使用nonce（时间戳）作为签名内容
        console.log('请求钱包签名，使用时间戳作为签名内容:', nonce);
        const encodedMessage = new TextEncoder().encode(nonce);
        
        // 请求签名
        const signResult = await phantomProvider.signMessage(encodedMessage, 'utf8');
        
        // 将签名结果转换为Base64字符串
        signature = btoa(String.fromCharCode.apply(null, signResult.signature));
        console.log('签名成功，签名值：', signature.substring(0, 15) + '...');
      } catch (error) {
        console.error('与钱包交互时出错:', error);
        
        // 如果是权限相关错误，提供更具体的解决方案
        const errorMsg = String(error).toLowerCase();
        if (errorMsg.includes('permission') || errorMsg.includes('not allowed')) {
          return {
            success: false,
            error: '钱包权限错误，请在钱包扩展中允许此网站访问'
          };
        } else if (errorMsg.includes('user rejected')) {
          return {
            success: false,
            error: '用户拒绝了连接请求'
          };
        } else {
          return {
            success: false,
            error: `钱包连接错误: ${error instanceof Error ? error.message : String(error)}`
          };
        }
      }
    }
    
    // 存储钱包信息到localStorage
    const walletInfo = {
      address,
      nonce,
      signature,
      connectedAt: Date.now(),
      expiryDate: expiryDate
    };
    
    localStorage.setItem(WALLET_KEY, JSON.stringify(walletInfo));
    console.log('钱包连接成功:', address);
    
    return {
      success: true,
      address,
      nonce,
      signature
    };
  } catch (error) {
    console.error('钱包连接失败:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

/**
 * 断开钱包连接
 */
export function disconnectWallet(): void {
  localStorage.removeItem(WALLET_KEY);
  console.log('钱包已断开连接');
}

/**
 * 获取剩余有效时间（毫秒）
 * @returns 剩余有效时间或0
 */
export function getRemainingValidTime(): number {
  const expiryTime = getSignatureExpiryTime();
  if (!expiryTime) return 0;
  
  const remainingTime = expiryTime - Date.now();
  return Math.max(0, remainingTime);
}

/**
 * 格式化持续时间为易读字符串
 * @param duration 持续时间（毫秒）
 * @returns 格式化后的字符串
 */
export function formatDuration(duration: number): string {
  if (duration <= 0) return '已过期';
  
  const seconds = Math.floor(duration / 1000) % 60;
  const minutes = Math.floor(duration / (1000 * 60)) % 60;
  const hours = Math.floor(duration / (1000 * 60 * 60)) % 24;
  const days = Math.floor(duration / (1000 * 60 * 60 * 24));
  
  const parts = [];
  if (days > 0) parts.push(`${days}天`);
  if (hours > 0) parts.push(`${hours}小时`);
  if (minutes > 0) parts.push(`${minutes}分钟`);
  if (seconds > 0 && days === 0) parts.push(`${seconds}秒`);
  
  return parts.join(' ');
}

/**
 * 刷新签名（如果即将过期）
 * @param minimumValidTime 最小有效时间（毫秒），默认1小时
 * @returns 刷新结果
 */
export async function refreshSignatureIfNeeded(minimumValidTime: number = 60 * 60 * 1000): Promise<boolean> {
  // 获取剩余有效时间
  const remainingTime = getRemainingValidTime();
  
  // 如果剩余时间小于最小有效时间，刷新签名
  if (remainingTime < minimumValidTime) {
    console.log(`签名剩余有效期不足（${formatDuration(remainingTime)}），重新签名...`);
    
    try {
      // 获取之前的过期持续时间
      const expiryTime = getSignatureExpiryTime();
      let duration = EXPIRY_PRESETS.DAY_7; // 默认7天
      
      if (expiryTime) {
        // 计算原始过期时间的持续时间
        const walletData = localStorage.getItem(WALLET_KEY);
        const connectedTime = walletData ? 
          JSON.parse(walletData).connectedAt || Date.now() : 
          Date.now();
        
        const originalDuration = expiryTime - connectedTime;
        duration = Math.max(EXPIRY_PRESETS.DAY_7, originalDuration); // 至少保持7天
      }
      
      // 确保参数是数字类型
      const result = await connectAndSign(duration as number);
      return result.success;
    } catch (error) {
      console.error('自动刷新签名失败:', error);
      return false;
    }
  }
  
  return true;
}

export default {
  isWalletConnected,
  getWalletAddress,
  getSignatureInfo,
  isSignatureExpired,
  connectAndSign,
  disconnectWallet,
  refreshSignatureIfNeeded,
  getSignatureExpiryTime,
  getRemainingValidTime,
  formatDuration,
  EXPIRY_PRESETS
}; 