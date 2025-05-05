<template>
  <div class="phantom-wallet">
    <button 
      v-if="!isConnected" 
      @click="connectWallet" 
      class="connect-button"
      :disabled="connecting"
    >
      <i class="wallet-icon"></i>
      {{ connecting ? '连接中...' : '连接钱包' }}
    </button>
    
    <!-- 内网环境下的备用选项 -->
    <div v-if="showConnectionHelp" class="connection-help-container">
      <div class="connection-help-tooltip">
        <div class="connection-help-header">
          <span>内网连接问题？</span>
          <button @click="closeConnectionHelp" class="close-btn">×</button>
        </div>
        <div class="connection-help-content">
          <p>在内网环境中使用钱包时可能会遇到连接问题，请尝试以下解决方案：</p>
          <ol>
            <li>确保已在 Chrome 商店安装最新版的 Phantom 钱包扩展</li>
            <li>访问 <code>chrome://extensions</code>，找到 Phantom 钱包</li>
            <li>开启"允许访问文件网址"，并确保"网站访问权限"设置为"在所有网站上"</li>
            <li>如果使用 HTTP 协议访问，尝试切换到 HTTPS</li>
          </ol>
          <div class="debug-options">
            <button @click="useDebugMode" class="debug-mode-btn">使用调试模式</button>
            <small>（此选项仅为测试使用，不会产生真实的区块链交易）</small>
          </div>
        </div>
      </div>
    </div>
    
    <div v-else-if="needsSignature" class="wallet-info needs-signature">
      <div class="address-display">
        {{ formatAddress(walletAddress) }}
      </div>
      <button @click="promptSignature" class="signature-button">
        <i class="signature-icon"></i>
        需要签名
      </button>
    </div>
    
    <div v-else class="wallet-info">
      <div class="address-display">
        {{ formatAddress(walletAddress) }}
        <span v-if="remainingTimeDisplay" class="expiry-display" :class="expiryStatusClass">
          <i class="time-icon"></i>
          {{ remainingTimeDisplay }}
        </span>
      </div>
      <button @click="disconnectWallet" class="disconnect-button">
        <i class="disconnect-icon"></i>
      </button>
    </div>
    
    <!-- 签名对话框 -->
    <div v-if="showSigningDialog" class="signing-dialog-backdrop">
      <div class="signing-dialog">
        <h3>钱包签名</h3>
        <p>{{ signingMessage }}</p>
        <p class="signing-detail">您将对一个时间戳进行签名，该时间戳代表签名的过期时间。</p>
        
        <!-- 签名有效期选择 -->
        <div class="expiry-options">
          <p>选择签名有效期：</p>
          <div class="option-buttons">
            <button 
              v-for="option in expiryOptions" 
              :key="option.value"
              @click="selectExpiryOption(option.value)"
              :class="['option-btn', { selected: selectedExpiry === option.value }]"
            >
              {{ option.label }}
            </button>
          </div>
          
          <!-- 自定义有效期设置 -->
          <div v-if="isCustomExpiry" class="custom-expiry-inputs">
            <div class="input-group">
              <input 
                v-model.number="customDays" 
                type="number" 
                min="0" 
                max="365"
                @change="updateCustomExpiry"
              />
              <label>天</label>
            </div>
            <div class="input-group">
              <input 
                v-model.number="customHours" 
                type="number" 
                min="0" 
                max="23"
                @change="updateCustomExpiry"
              />
              <label>时</label>
            </div>
            <div class="input-group">
              <input 
                v-model.number="customMinutes" 
                type="number" 
                min="0" 
                max="59"
                @change="updateCustomExpiry"
              />
              <label>分</label>
            </div>
            <div class="input-group">
              <input 
                v-model.number="customSeconds" 
                type="number" 
                min="0" 
                max="59"
                @change="updateCustomExpiry"
              />
              <label>秒</label>
            </div>
          </div>
          
          <div class="expiry-summary">
            签名有效期至：{{ expiryDateDisplay }}
          </div>
        </div>
        
        <div class="signature-note">
          <i class="info-icon"></i>
          <span>所有接口操作都需要有效的钱包签名</span>
        </div>
        <div class="signing-actions">
          <button @click="closeSigningDialog" class="cancel-button">取消</button>
          <button @click="confirmSigning" class="sign-button" :disabled="signingInProgress">
            {{ signingInProgress ? '签名中...' : '签名' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, watch, onMounted, computed } from 'vue';
import {
  isWalletConnected,
  getWalletAddress,
  connectAndSign,
  disconnectWallet as disconnectWalletFn,
  isSignatureExpired,
  getSignatureExpiryTime,
  getRemainingValidTime,
  formatDuration,
  EXPIRY_PRESETS
} from '../services/solana-wallet';

export default defineComponent({
  name: 'PhantomWallet',
  emits: [
    'wallet-connected', 
    'wallet-disconnected'
  ],
  
  setup(props, { emit }) {
    // 连接状态
    const isConnected = ref(false);
    const walletAddress = ref('');
    const connecting = ref(false);
    
    // 内网连接帮助状态
    const showConnectionHelp = ref(false);
    const connectionAttempts = ref(0);
    
    // 签名对话框状态
    const showSigningDialog = ref(false);
    const signingMessage = ref('');
    const signingInProgress = ref(false);
    const checkingExpiry = ref(false);
    
    // 签名过期设置
    const selectedExpiry = ref(EXPIRY_PRESETS.DAY_7.toString());
    const customDays = ref(7);
    const customHours = ref(0);
    const customMinutes = ref(0);
    const customSeconds = ref(0);
    
    // 计算属性
    const isCustomExpiry = computed(() => selectedExpiry.value === 'custom');
    
    const effectiveExpiry = computed(() => {
      if (isCustomExpiry.value) {
        return (
          customDays.value * 24 * 60 * 60 * 1000 +
          customHours.value * 60 * 60 * 1000 +
          customMinutes.value * 60 * 1000 +
          customSeconds.value * 1000
        );
      } else {
        return parseInt(selectedExpiry.value);
      }
    });
    
    const expiryDateDisplay = computed(() => {
      const timestamp = Date.now() + effectiveExpiry.value;
      return new Date(timestamp).toLocaleString();
    });
    
    const needsSignature = computed(() => isConnected.value && isSignatureExpired());
    
    const remainingTime = computed(() => {
      if (!isConnected.value) return 0;
      return getRemainingValidTime();
    });
    
    const remainingTimeDisplay = computed(() => {
      if (remainingTime.value <= 0) return '';
      return formatDuration(remainingTime.value);
    });
    
    const expiryStatusClass = computed(() => {
      const oneDay = 24 * 60 * 60 * 1000;
      if (remainingTime.value <= oneDay) return 'expiry-warning';
      return 'expiry-normal';
    });
    
    // 检查连接状态
    const checkConnection = () => {
      isConnected.value = isWalletConnected();
      const address = getWalletAddress();
      if (address) {
        walletAddress.value = address;
        emit('wallet-connected', walletAddress.value);
      }
    };

    // 连接钱包
    const connectWallet = async () => {
      try {
        connecting.value = true;
        const result = await connectAndSign(effectiveExpiry.value);
        
        if (result.success && result.address) {
          isConnected.value = true;
          walletAddress.value = result.address;
          emit('wallet-connected', result.address);
          // 连接成功，重置连接尝试次数
          connectionAttempts.value = 0;
          showConnectionHelp.value = false;
        } else if (result.error) {
          console.error('钱包连接失败:', result.error);
          // 记录连接尝试次数
          connectionAttempts.value++;
          
          // 如果连续失败2次，显示连接帮助
          if (connectionAttempts.value >= 2) {
            showConnectionHelp.value = true;
          }
          
          // 如果错误信息包含权限或无法找到钱包的提示，直接显示帮助
          if (typeof result.error === 'string' && (
              result.error.includes('权限') || 
              result.error.includes('钱包') || 
              result.error.includes('not found') || 
              result.error.includes('未检测'))) {
            showConnectionHelp.value = true;
          }
        }
      } catch (error) {
        console.error('连接钱包出错:', error);
        // 出错时也增加尝试次数
        connectionAttempts.value++;
        if (connectionAttempts.value >= 2) {
          showConnectionHelp.value = true;
        }
      } finally {
        connecting.value = false;
      }
    };
    
    // 关闭连接帮助
    const closeConnectionHelp = () => {
      showConnectionHelp.value = false;
    };
    
    // 使用调试模式
    const useDebugMode = () => {
      console.log('启用钱包调试模式');
      localStorage.setItem('wallet_debug_mode', 'true');
      // 重新尝试连接
      connectWallet();
    };
    
    // 显示签名对话框
    const showSignDialog = (message: string = '请签名以验证您的身份') => {
      signingMessage.value = message;
      showSigningDialog.value = true;
      
      // 从当前签名状态加载过期时间设置
      const expiryTime = getSignatureExpiryTime();
      if (expiryTime) {
        const duration = expiryTime - Date.now();
        if (duration > 0) {
          // 根据剩余时间设置最接近的预设选项
          if (duration <= EXPIRY_PRESETS.DAY_7) {
            selectExpiryOption(EXPIRY_PRESETS.DAY_7.toString());
          } else if (duration <= EXPIRY_PRESETS.DAY_30) {
            selectExpiryOption(EXPIRY_PRESETS.DAY_30.toString());
          } else if (duration <= EXPIRY_PRESETS.DAY_90) {
            selectExpiryOption(EXPIRY_PRESETS.DAY_90.toString());
          } else {
            // 转换为自定义设置
            selectExpiryOption('custom');
            const days = Math.floor(duration / (24 * 60 * 60 * 1000));
            const hours = Math.floor((duration % (24 * 60 * 60 * 1000)) / (60 * 60 * 1000));
            const minutes = Math.floor((duration % (60 * 60 * 1000)) / (60 * 1000));
            const seconds = Math.floor((duration % (60 * 1000)) / 1000);
            
            customDays.value = days;
            customHours.value = hours;
            customMinutes.value = minutes;
            customSeconds.value = seconds;
          }
        }
      }
    };
    
    // 选择过期选项
    const selectExpiryOption = (value: string) => {
      selectedExpiry.value = value;
    };
    
    // 更新自定义过期设置
    const updateCustomExpiry = () => {
      customDays.value = Math.max(0, customDays.value);
      customHours.value = Math.max(0, Math.min(23, customHours.value));
      customMinutes.value = Math.max(0, Math.min(59, customMinutes.value));
      customSeconds.value = Math.max(0, Math.min(59, customSeconds.value));
    };
    
    // 提示用户签名
    const promptSignature = () => {
      showSignDialog('所有接口操作都需要有效的钱包签名，请签名以继续使用');
    };

    // 断开钱包连接
    const disconnectWallet = () => {
      disconnectWalletFn();
      isConnected.value = false;
      walletAddress.value = '';
      emit('wallet-disconnected');
    };

    // 格式化钱包地址显示
    const formatAddress = (address: string): string => {
      if (!address) return '';
      return `${address.substring(0, 4)}...${address.substring(address.length - 4)}`;
    };
    
    // 关闭签名对话框
    const closeSigningDialog = () => {
      showSigningDialog.value = false;
    };

    // 确认签名
    const confirmSigning = async () => {
      try {
        signingInProgress.value = true;
        const result = await connectAndSign(effectiveExpiry.value);
        
        if (result.success) {
          closeSigningDialog();
          // 如果钱包地址发生变化，发出事件
          if (result.address && result.address !== walletAddress.value) {
            walletAddress.value = result.address;
            emit('wallet-connected', result.address);
          }
        } else {
          console.error('签名失败:', result.error);
        }
      } catch (error) {
        console.error('签名过程出错:', error);
      } finally {
        signingInProgress.value = false;
      }
    };

    // 检查签名是否过期
    const checkSignatureExpiry = () => {
      if (checkingExpiry.value) return;
      
      checkingExpiry.value = true;
      try {
        if (isConnected.value && isSignatureExpired()) {
          // 只更新状态，不自动弹出签名对话框
          // 用户可以看到UI上显示"需要签名"的状态，并自行决定是否点击签名按钮
          console.log('签名已过期，UI将显示需要签名状态');
        }
      } finally {
        checkingExpiry.value = false;
      }
    };

    // 监听签名错误事件
    const handleSignatureError = (event: CustomEvent) => {
      // 不主动弹出签名对话框，只记录错误
      console.log('签名验证失败:', event.detail.message || '请重新签名');
      // 确保needsSignature计算属性反映当前状态
      checkConnection();
    };

    // 组件挂载时
    onMounted(() => {
      // 检查初始连接状态
      checkConnection();
      
      // 添加事件监听
      window.addEventListener('signature-error', handleSignatureError as EventListener);
      
      // 定期检查签名是否过期
      const expiryInterval = setInterval(checkSignatureExpiry, 60000); // 每分钟检查一次
      
      // 组件卸载时清理
      return () => {
        clearInterval(expiryInterval);
        window.removeEventListener('signature-error', handleSignatureError as EventListener);
      };
    });

    // 当连接状态变化时发出事件
    watch(isConnected, (newValue) => {
      if (!newValue) {
        emit('wallet-disconnected');
      }
    });

    return {
      isConnected,
      walletAddress,
      connecting,
      showConnectionHelp,
      signingMessage,
      signingInProgress,
      showSigningDialog,
      needsSignature,
      remainingTimeDisplay,
      expiryStatusClass,
      expiryOptions: [
        { value: EXPIRY_PRESETS.DAY_7.toString(), label: '7天' },
        { value: EXPIRY_PRESETS.DAY_30.toString(), label: '30天' },
        { value: EXPIRY_PRESETS.DAY_90.toString(), label: '90天' },
        { value: 'custom', label: '自定义' }
      ],
      selectedExpiry,
      customDays,
      customHours,
      customMinutes,
      customSeconds,
      isCustomExpiry,
      expiryDateDisplay,
      connectWallet,
      disconnectWallet,
      promptSignature,
      formatAddress,
      closeSigningDialog,
      confirmSigning,
      selectExpiryOption,
      updateCustomExpiry,
      closeConnectionHelp,
      useDebugMode
    };
  }
});
</script>

<style scoped>
.phantom-wallet {
  display: flex;
  align-items: center;
}

.connect-button, .disconnect-button, .signature-button {
  background-color: #512da8;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 8px 16px;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: background-color 0.2s;
}

.connect-button:hover, .disconnect-button:hover {
  background-color: #673ab7;
}

.connect-button:disabled {
  background-color: #9e9e9e;
  cursor: not-allowed;
}

.wallet-info {
  display: flex;
  align-items: center;
  background-color: rgba(81, 45, 168, 0.1);
  padding: 4px 8px;
  border-radius: 4px;
}

.wallet-info.needs-signature {
  background-color: rgba(255, 152, 0, 0.1);
  border: 1px solid rgba(255, 152, 0, 0.3);
}

.address-display {
  font-size: 14px;
  margin-right: 8px;
  color: #512da8;
  font-weight: 500;
  display: flex;
  align-items: center;
}

.expiry-display {
  margin-left: 8px;
  font-size: 12px;
  display: flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 3px;
}

.expiry-normal {
  color: #388e3c;
  background-color: rgba(56, 142, 60, 0.1);
}

.expiry-warning {
  color: #f57c00;
  background-color: rgba(245, 124, 0, 0.1);
}

.needs-signature .address-display {
  color: #f57c00;
}

.signature-button {
  background-color: #f57c00;
  padding: 4px 8px;
  font-size: 12px;
}

.signature-button:hover {
  background-color: #ff9800;
}

.disconnect-button {
  padding: 4px 8px;
  font-size: 12px;
  background-color: transparent;
  color: #d32f2f;
}

.disconnect-button:hover {
  background-color: rgba(211, 47, 47, 0.1);
}

.wallet-icon, .disconnect-icon, .signature-icon, .info-icon, .time-icon {
  display: inline-block;
  width: 16px;
  height: 16px;
  margin-right: 6px;
}

.wallet-icon {
  background-color: white;
  mask: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxyZWN0IHg9IjIiIHk9IjQiIHdpZHRoPSIyMCIgaGVpZ2h0PSIxNiIgcng9IjIiPjwvcmVjdD48cGF0aCBkPSJNMTYgMTJWOSI+PC9wYXRoPjxwYXRoIGQ9Ik0xNiAxNkg5ICI+PC9wYXRoPjwvc3ZnPg==');
  mask-size: cover;
}

.disconnect-icon {
  background-color: #d32f2f;
  mask: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik05IDE3SDVhMiAyIDAgMCAxLTItMlY1YTIgMiAwIDAgMSAyLTJoNCI+PC9wYXRoPjxwb2x5bGluZSBwb2ludHM9IjE2IDcgMjEgMTIgMTYgMTciPjwvcG9seWxpbmU+PHBhdGggZD0iTTIxIDEySDgiPjwvcGF0aD48L3N2Zz4=');
  mask-size: cover;
}

.signature-icon {
  background-color: white;
  mask: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0xNSA2djEyYTMgMyAwIDEgMCA2IDB2LTIiLz48cGF0aCBkPSJNMjEgNnYxMmEzIDMgMCAwIDEtNiAwdi0yIi8+PHBhdGggZD0iTTMgMTJBMiAyIDAgMCAxIDUgMTBoMTRhMiAyIDAgMCAxIDIgMnY4YTIgMiAwIDAgMS0yIDJINSIvPjwvc3ZnPg==');
  mask-size: cover;
}

.info-icon {
  background-color: #1565c0;
  mask: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjEwIj48L2NpcmNsZT48bGluZSB4MT0iMTIiIHkxPSIxNiIgeDI9IjEyIiB5Mj0iMTIiPjwvbGluZT48bGluZSB4MT0iMTIiIHkxPSI4IiB4Mj0iMTIuMDEiIHkyPSI4Ij48L2xpbmU+PC9zdmc+');
  mask-size: cover;
}

.time-icon {
  mask: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjEwIj48L2NpcmNsZT48cG9seWxpbmUgcG9pbnRzPSIxMiA2IDEyIDEyIDE2IDE0Ij48L3BvbHlsaW5lPjwvc3ZnPg==');
  mask-size: cover;
  width: 14px;
  height: 14px;
}

.expiry-normal .time-icon {
  background-color: #388e3c;
}

.expiry-warning .time-icon {
  background-color: #f57c00;
}

/* 签名对话框样式 */
.signing-dialog-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.signing-dialog {
  background-color: white;
  border-radius: 8px;
  padding: 24px;
  max-width: 500px;
  width: 90%;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.signing-dialog h3 {
  margin-top: 0;
  color: #512da8;
}

.signing-dialog h4 {
  font-size: 14px;
  margin: 16px 0 8px;
  color: #333;
}

.expiry-options {
  margin-top: 16px;
  background-color: #f5f5f5;
  padding: 16px;
  border-radius: 4px;
}

.option-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.option-btn {
  padding: 8px 12px;
  background-color: #e0e0e0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 14px;
}

.option-btn:hover {
  background-color: #d0d0d0;
}

.option-btn.selected {
  background-color: #512da8;
  color: white;
}

.custom-expiry-inputs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
  padding: 12px;
  background-color: rgba(81, 45, 168, 0.05);
  border-radius: 4px;
}

.input-group {
  display: flex;
  align-items: center;
}

.input-group input {
  width: 60px;
  padding: 6px;
  border: 1px solid #ccc;
  border-radius: 4px;
  text-align: center;
}

.input-group label {
  margin-left: 4px;
  font-size: 14px;
  color: #555;
}

.expiry-summary {
  margin-top: 12px;
  font-size: 14px;
  color: #555;
}

.signature-note {
  margin-top: 16px;
  padding: 10px;
  background-color: rgba(21, 101, 192, 0.1);
  border-left: 3px solid #1565c0;
  border-radius: 3px;
  display: flex;
  align-items: center;
  font-size: 13px;
  color: #1565c0;
}

.signing-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 24px;
  gap: 12px;
}

.cancel-button {
  background-color: #f5f5f5;
  color: #616161;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.sign-button {
  background-color: #512da8;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.sign-button:disabled {
  background-color: #9e9e9e;
  cursor: not-allowed;
}

.signing-detail {
  margin-top: 16px;
  font-size: 13px;
  color: #555;
}

/* 内网连接帮助样式 */
.connection-help-container {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 1000;
  margin-top: 8px;
}

.connection-help-tooltip {
  width: 360px;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  border: 1px solid #e0e0e0;
  overflow: hidden;
}

.connection-help-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background-color: #f5f5f5;
  border-bottom: 1px solid #e0e0e0;
  font-weight: 500;
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #757575;
}

.connection-help-content {
  padding: 16px;
}

.connection-help-content p {
  margin-top: 0;
  margin-bottom: 12px;
  color: #616161;
}

.connection-help-content ol {
  margin: 0;
  padding-left: 20px;
}

.connection-help-content li {
  margin-bottom: 8px;
  color: #616161;
}

.connection-help-content code {
  background-color: #f5f5f5;
  padding: 2px 4px;
  border-radius: 3px;
  font-family: monospace;
}

.debug-options {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed #e0e0e0;
  text-align: center;
}

.debug-mode-btn {
  background-color: #ff9800;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 8px;
}

.debug-mode-btn:hover {
  background-color: #f57c00;
}

.debug-options small {
  display: block;
  color: #9e9e9e;
  font-size: 12px;
}
</style> 