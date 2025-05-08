/**
 * 元数据代理服务
 * 用于解决CORS问题，通过本地服务器代理请求元数据
 */

/**
 * 通过代理获取元数据
 * @param originalUrl 原始元数据URL
 * @returns 元数据对象
 */
export async function fetchMetadataViaProxy(originalUrl: string): Promise<any> {
  try {
    // 检查URL是否是IP地址形式
    const isIpUrl = /^https?:\/\/\d+\.\d+\.\d+\.\d+(:\d+)?\//.test(originalUrl);
    
    if (isIpUrl) {
      console.log('检测到IP地址形式的URL，使用代理...');
      
      // 提取路径部分
      const urlObj = new URL(originalUrl);
      const pathWithQuery = urlObj.pathname + urlObj.search;
      
      // 构建代理URL
      const proxyUrl = `/api/metadata-proxy${pathWithQuery}`;
      console.log('代理URL:', proxyUrl);
      
      // 发送请求
      const response = await fetch(proxyUrl, {
        method: 'GET',
        headers: {
          'Accept': 'application/json'
        }
      });
      
      if (!response.ok) {
        throw new Error(`代理请求失败: ${response.status} ${response.statusText}`);
      }
      
      return await response.json();
    } else {
      // 非IP地址形式的URL，直接请求
      console.log('使用直接请求...');
      const response = await fetch(originalUrl, {
        method: 'GET',
        headers: {
          'Accept': 'application/json'
        }
      });
      
      if (!response.ok) {
        throw new Error(`请求失败: ${response.status} ${response.statusText}`);
      }
      
      return await response.json();
    }
  } catch (error) {
    console.error('获取元数据失败:', error);
    throw error;
  }
}

export default {
  fetchMetadataViaProxy
}; 