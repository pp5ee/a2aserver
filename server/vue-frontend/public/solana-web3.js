// 加载Solana Web3.js库
(function() {
  if (typeof window.solanaWeb3 !== 'undefined') {
    return;
  }
  
  // 动态加载Web3.js脚本
  const script = document.createElement('script');
  script.src = 'https://unpkg.com/@solana/web3.js@latest/lib/index.iife.min.js';
  script.async = true;
  script.onload = function() {
    // Web3.js库加载完成
    console.log('Solana Web3.js 加载成功');
    
    // 触发自定义事件
    const event = new Event('solanaWeb3Loaded');
    window.dispatchEvent(event);
  };
  script.onerror = function() {
    console.error('Solana Web3.js 加载失败');
  };
  
  document.head.appendChild(script);
})(); 