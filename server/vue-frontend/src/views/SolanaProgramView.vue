<template>
  <div class="solana-program-view">
    <h1>Solana Program</h1>
    
    <div class="wallet-section">
      <PhantomWallet @wallet-connected="handleWalletConnected" @wallet-disconnected="handleWalletDisconnected" />
    </div>
    
    <div v-if="isWalletConnected" class="program-sections">
      <!-- 程序信息 -->
      <div class="info-section">
        <h2>Program Info</h2>
        <div class="info-item">
          <span class="label">Program ID:</span>
          <span class="value">{{ programInfo.programId }}</span>
        </div>
        <div class="info-item">
          <span class="label">Network:</span>
          <span class="value">{{ programInfo.network }}</span>
        </div>
      </div>
      
      <!-- 铸造NFT部分 -->
      <div class="section mint-section">
        <h2>Mint New Agent NFT</h2>
        <div class="input-group">
          <label>Metadata URL:</label>
          <input v-model="metadataUrl" placeholder="https://www.samplea2agent.com" />
          <small class="form-helper">请输入有效的元数据URL，支持http://或https://开头，支持域名(如samplea2agent.com)、域名+端口(如example.com:8080)或IP+端口(如8.214.38.69:10003)格式</small>
        </div>
        <button @click="mintNFT" :disabled="mintingInProgress || !isValidMetadataUrl">
          {{ mintingInProgress ? 'Minting...' : 'Mint NFT' }}
        </button>
        
        <div v-if="mintResult && mintResult.success" class="result success">
          <h3>Mint Successful!</h3>
          <div class="result-item">
            <span class="label">NFT Mint:</span>
            <span class="value">{{ mintResult.nftMint }}</span>
          </div>
          <div class="result-item">
            <span class="label">Transaction:</span>
            <a :href="'https://explorer.solana.com/tx/' + mintResult.transactionSignature + '?cluster=devnet'" 
               target="_blank" class="tx-link">
              View on Explorer
            </a>
          </div>
          
          <!-- 添加元数据查看器 -->
          <NftMetadataViewer 
            v-if="mintResult.metadata && mintResult.metadata.metadataUrl" 
            :metadataUrl="mintResult.metadata.metadataUrl" 
          />
        </div>
        
        <div v-if="mintResult && !mintResult.success" class="result error">
          <h3>Mint Failed</h3>
          <p>{{ mintResult.error }}</p>
        </div>
      </div>
      
      <!-- 购买订阅部分 -->
      <div class="section subscription-section">
        <h2>Purchase Subscription</h2>
        <div class="input-group">
          <label>Agent NFT Mint:</label>
          <input v-model="subscriptionNftMint" placeholder="NFT Mint Address" />
        </div>
        <div class="input-group">
          <label>Subscription Type:</label>
          <select v-model="subscriptionType">
            <option value="oneDay">One Day (1 SOL)</option>
            <option value="sevenDays">Seven Days (5 SOL)</option>
            <option value="thirtyDays">Thirty Days (15 SOL)</option>
            <option value="yearly">One Year (100 SOL)</option>
          </select>
        </div>
        <button @click="purchaseSub" :disabled="purchasingInProgress">
          {{ purchasingInProgress ? 'Processing...' : 'Purchase Subscription' }}
        </button>
        
        <div v-if="purchaseResult && purchaseResult.success" class="result success">
          <h3>Purchase Successful!</h3>
          <div class="result-item">
            <span class="label">Subscription ID:</span>
            <span class="value">{{ purchaseResult.subscriptionPDA }}</span>
          </div>
          <div class="result-item">
            <span class="label">Expires At:</span>
            <span class="value">{{ purchaseResult.expiresAt }}</span>
          </div>
          <div class="result-item">
            <span class="label">Transaction:</span>
            <a :href="'https://explorer.solana.com/tx/' + purchaseResult.transactionSignature + '?cluster=devnet'" 
               target="_blank" class="tx-link">
              View on Explorer
            </a>
          </div>
        </div>
        
        <div v-if="purchaseResult && !purchaseResult.success" class="result error">
          <h3>Purchase Failed</h3>
          <p>{{ purchaseResult.error }}</p>
        </div>
      </div>
      
      <!-- 查询部分 -->
      <div class="section query-section">
        <h2>Query</h2>
        
        <div class="query-actions">
          <button @click="fetchAllNFTs" :disabled="loadingNFTs">
            {{ loadingNFTs ? 'Loading...' : 'Get All Agent NFTs' }}
          </button>
          
          <button @click="fetchUserSubscriptions" :disabled="loadingSubscriptions">
            {{ loadingSubscriptions ? 'Loading...' : 'Get My Subscriptions' }}
          </button>
        </div>
        
        <!-- NFT 展示 -->
        <div v-if="allNFTs.length > 0" class="query-results nft-results">
          <h3>All Agent NFTs</h3>
          <div class="nft-grid">
            <div v-for="(nft, index) in allNFTs" :key="index" class="nft-card">
              <div class="nft-header">NFT #{{ index + 1 }}</div>
              <div class="nft-content">
                <div class="nft-item">
                  <span class="label">Address:</span>
                  <span class="value trimmed">{{ nft.address }}</span>
                </div>
                <div class="nft-item">
                  <span class="label">Owner:</span>
                  <span class="value trimmed">{{ nft.owner }}</span>
                </div>
                <div class="nft-item">
                  <span class="label">Mint:</span>
                  <span class="value trimmed">{{ nft.mint }}</span>
                </div>
                <div class="nft-item">
                  <span class="label">Metadata:</span>
                  <span class="value trimmed" :title="nft.metadataUrl">{{ nft.metadataUrl }}</span>
                </div>
                <div class="nft-actions">
                  <button @click="checkSubscription(nft.mint)" class="check-sub-btn">
                    Check My Subscription
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 订阅展示 -->
        <div v-if="userSubscriptions.length > 0" class="query-results sub-results">
          <h3>My Subscriptions</h3>
          <div class="sub-list">
            <div v-for="(sub, index) in userSubscriptions" :key="index" class="sub-card">
              <div class="sub-header">Subscription #{{ index + 1 }}</div>
              <div class="sub-content">
                <div class="sub-item">
                  <span class="label">Address:</span>
                  <span class="value trimmed">{{ sub.address }}</span>
                </div>
                <div class="sub-item">
                  <span class="label">Agent NFT:</span>
                  <span class="value trimmed">{{ sub.agentNftMint }}</span>
                </div>
                <div class="sub-item">
                  <span class="label">Expires At:</span>
                  <span class="value">{{ sub.expiresAt }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 单个订阅查询结果 -->
        <div v-if="singleSubscriptionResult" class="query-results single-sub-result">
          <h3>Subscription Check Result</h3>
          
          <div v-if="singleSubscriptionResult.hasSubscription" class="sub-details">
            <div class="sub-item">
              <span class="label">Status:</span>
              <span class="value status active">Active</span>
            </div>
            <div class="sub-item">
              <span class="label">Agent NFT:</span>
              <span class="value trimmed">{{ singleSubscriptionResult.subscription.agentNftMint }}</span>
            </div>
            <div class="sub-item">
              <span class="label">Expires At:</span>
              <span class="value">{{ singleSubscriptionResult.subscription.expiresAt }}</span>
            </div>
          </div>
          
          <div v-else class="no-subscription">
            <p>You don't have an active subscription for this Agent NFT.</p>
            <button @click="setSubscriptionNftMint(checkedNftMint)" class="purchase-now-btn">
              Purchase Now
            </button>
          </div>
        </div>
        
        <div v-if="queryError" class="result error">
          <p>{{ queryError }}</p>
        </div>
      </div>
    </div>
    
    <div v-else-if="!isWalletConnected" class="wallet-prompt">
      <p>Please connect your wallet to use the Solana Program features.</p>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed } from 'vue';
import PhantomWallet from '@/components/PhantomWallet.vue';
import NftMetadataViewer from '@/components/NftMetadataViewer.vue';
import { isWalletConnected as checkWalletConnection, getWalletAddress } from '@/services/solana-wallet';
import { 
  mintAgentNFT, 
  purchaseSubscription, 
  getAllAgentNFTs, 
  getUserSubscriptions,
  getUserAgentSubscription,
  getProgramInfo
} from '@/services/solana-program';

interface NFT {
  address: string;
  owner: string;
  mint: string;
  metadataUrl: string;
}

interface Subscription {
  address: string;
  user: string;
  agentNftMint: string;
  expiresAt: string;
}

interface MintResult {
  success: boolean;
  nftMint?: string;
  agentNftPDA?: string;
  transactionSignature?: string;
  metadata?: {
    owner: string;
    mint: string;
    metadataUrl: string;
  };
  error?: string;
}

interface PurchaseResult {
  success: boolean;
  subscriptionPDA?: string;
  transactionSignature?: string;
  expiresAt?: string;
  error?: string;
}

interface SubscriptionResult {
  success: boolean;
  hasSubscription: boolean;
  subscription?: {
    address: string;
    user: string;
    agentNftMint: string;
    expiresAt: string;
  };
  error?: string;
}

export default defineComponent({
  name: 'SolanaProgramView',
  
  components: {
    PhantomWallet,
    NftMetadataViewer
  },
  
  setup() {
    // 钱包状态
    const isWalletConnected = ref(false);
    const walletAddress = ref('');
    
    // 程序信息
    const programInfo = ref({
      programId: '',
      network: ''
    });
    
    // 铸造NFT状态
    const metadataUrl = ref('');
    const mintingInProgress = ref(false);
    const mintResult = ref<MintResult | null>(null);
    
    // 购买订阅状态
    const subscriptionNftMint = ref('');
    const subscriptionType = ref('sevenDays');
    const purchasingInProgress = ref(false);
    const purchaseResult = ref<PurchaseResult | null>(null);
    
    // 查询状态
    const loadingNFTs = ref(false);
    const loadingSubscriptions = ref(false);
    const allNFTs = ref<NFT[]>([]);
    const userSubscriptions = ref<Subscription[]>([]);
    const queryError = ref('');
    const singleSubscriptionResult = ref<SubscriptionResult | null>(null);
    const checkedNftMint = ref('');
    
    // 初始化
    onMounted(() => {
      checkWalletStatus();
      programInfo.value = getProgramInfo();
    });
    
    // 检查钱包状态
    const checkWalletStatus = () => {
      isWalletConnected.value = checkWalletConnection();
      if (isWalletConnected.value) {
        walletAddress.value = getWalletAddress() || '';
      }
    };
    
    // 处理钱包连接事件
    const handleWalletConnected = () => {
      checkWalletStatus();
    };
    
    // 处理钱包断开连接事件
    const handleWalletDisconnected = () => {
      isWalletConnected.value = false;
      walletAddress.value = '';
    };
    
    // 铸造NFT
    const mintNFT = async () => {
      if (!metadataUrl.value) {
        alert('Please enter a metadata URL');
        return;
      }
      
      mintingInProgress.value = true;
      mintResult.value = null;
      
      try {
        const result = await mintAgentNFT(metadataUrl.value);
        mintResult.value = result as MintResult;
        
        if (result.success) {
          // 如果铸造成功，刷新NFT列表
          fetchAllNFTs();
        }
      } catch (error) {
        mintResult.value = {
          success: false,
          error: error instanceof Error ? error.message : String(error)
        };
      } finally {
        mintingInProgress.value = false;
      }
    };
    
    // 购买订阅
    const purchaseSub = async () => {
      if (!subscriptionNftMint.value) {
        alert('Please enter an Agent NFT mint address');
        return;
      }
      
      purchasingInProgress.value = true;
      purchaseResult.value = null;
      
      try {
        const result = await purchaseSubscription(
          subscriptionNftMint.value,
          subscriptionType.value
        );
        
        purchaseResult.value = result as PurchaseResult;
        
        if (result.success) {
          // 如果购买成功，刷新订阅列表
          fetchUserSubscriptions();
        }
      } catch (error) {
        purchaseResult.value = {
          success: false,
          error: error instanceof Error ? error.message : String(error)
        };
      } finally {
        purchasingInProgress.value = false;
      }
    };
    
    // 获取所有NFTs
    const fetchAllNFTs = async () => {
      loadingNFTs.value = true;
      queryError.value = '';
      
      try {
        const result = await getAllAgentNFTs();
        
        if (result.success && result.agentNfts) {
          allNFTs.value = result.agentNfts as NFT[];
        } else {
          queryError.value = result.error || 'Failed to fetch NFTs';
          allNFTs.value = [];
        }
      } catch (error) {
        queryError.value = error instanceof Error ? error.message : String(error);
        allNFTs.value = [];
      } finally {
        loadingNFTs.value = false;
      }
    };
    
    // 获取用户订阅
    const fetchUserSubscriptions = async () => {
      loadingSubscriptions.value = true;
      queryError.value = '';
      
      try {
        const result = await getUserSubscriptions();
        
        if (result.success && result.subscriptions) {
          userSubscriptions.value = result.subscriptions as Subscription[];
        } else {
          queryError.value = result.error || 'Failed to fetch subscriptions';
          userSubscriptions.value = [];
        }
      } catch (error) {
        queryError.value = error instanceof Error ? error.message : String(error);
        userSubscriptions.value = [];
      } finally {
        loadingSubscriptions.value = false;
      }
    };
    
    // 检查特定NFT的订阅状态
    const checkSubscription = async (nftMint: string) => {
      singleSubscriptionResult.value = null;
      checkedNftMint.value = nftMint;
      queryError.value = '';
      
      try {
        const result = await getUserAgentSubscription(nftMint);
        
        if (result.success) {
          singleSubscriptionResult.value = result as SubscriptionResult;
        } else {
          queryError.value = result.error || 'Failed to check subscription';
        }
      } catch (error) {
        queryError.value = error instanceof Error ? error.message : String(error);
      }
    };
    
    // 设置订阅NFT Mint
    const setSubscriptionNftMint = (mint: string) => {
      subscriptionNftMint.value = mint;
      
      // 滚动到购买订阅部分
      const subscriptionSection = document.querySelector('.subscription-section');
      if (subscriptionSection) {
        subscriptionSection.scrollIntoView({ behavior: 'smooth' });
      }
    };
    
    // 添加验证逻辑
    const isValidMetadataUrl = computed(() => {
      return metadataUrl.value.startsWith('http://') || metadataUrl.value.startsWith('https://');
    });
    
    return {
      isWalletConnected,
      walletAddress,
      programInfo,
      metadataUrl,
      mintingInProgress,
      mintResult,
      subscriptionNftMint,
      subscriptionType,
      purchasingInProgress,
      purchaseResult,
      loadingNFTs,
      loadingSubscriptions,
      allNFTs,
      userSubscriptions,
      queryError,
      singleSubscriptionResult,
      checkedNftMint,
      handleWalletConnected,
      handleWalletDisconnected,
      mintNFT,
      purchaseSub,
      fetchAllNFTs,
      fetchUserSubscriptions,
      checkSubscription,
      setSubscriptionNftMint,
      isValidMetadataUrl
    };
  }
});
</script>

<style scoped>
.solana-program-view {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

h1 {
  font-size: 2.5rem;
  margin-bottom: 2rem;
  color: #344767;
}

.wallet-section {
  margin-bottom: 2rem;
  display: flex;
  justify-content: flex-end;
}

.program-sections {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;
}

.section {
  background-color: #ffffff;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  padding: 1.5rem;
  transition: all 0.3s ease;
}

.section h2 {
  font-size: 1.5rem;
  color: #344767;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid #e9ecef;
  padding-bottom: 0.75rem;
}

.info-section {
  background-color: #f1f5f9;
  border-left: 4px solid #3a86ff;
}

.info-item {
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
}

.label {
  font-weight: 600;
  margin-right: 0.5rem;
  color: #495057;
}

.value {
  color: #6c757d;
  word-break: break-all;
}

.value.trimmed {
  display: inline-block;
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: max-width 0.3s ease;
}

.value.trimmed:hover {
  max-width: 300px;
  overflow: visible;
  white-space: normal;
  word-break: break-all;
  position: relative;
  z-index: 10;
  background-color: #f8fafc;
  box-shadow: 0 2px 5px rgba(0,0,0,0.1);
  padding: 2px 5px;
  border-radius: 3px;
}

.input-group {
  margin-bottom: 1rem;
}

.input-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: #495057;
}

.input-group input,
.input-group select {
  width: 100%;
  padding: 0.75rem;
  border-radius: 6px;
  border: 1px solid #ced4da;
  font-size: 1rem;
}

button {
  background-color: #3a86ff;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.3s;
}

button:hover {
  background-color: #2a75ff;
}

button:disabled {
  background-color: #a0c4ff;
  cursor: not-allowed;
}

.result {
  margin-top: 1.5rem;
  padding: 1rem;
  border-radius: 6px;
}

.result.success {
  background-color: #d1fae5;
  border-left: 4px solid #10b981;
}

.result.error {
  background-color: #fee2e2;
  border-left: 4px solid #ef4444;
}

.result h3 {
  margin-bottom: 0.75rem;
  color: #344767;
}

.result-item {
  margin-bottom: 0.5rem;
}

.tx-link {
  color: #3a86ff;
  text-decoration: none;
  font-weight: 600;
}

.tx-link:hover {
  text-decoration: underline;
}

.query-actions {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.query-results {
  margin-top: 2rem;
}

.query-results h3 {
  font-size: 1.25rem;
  margin-bottom: 1rem;
  color: #344767;
}

.nft-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.nft-card, .sub-card {
  background-color: #f8fafc;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.3s;
}

.nft-card:hover, .sub-card:hover {
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.nft-header, .sub-header {
  background-color: #3a86ff;
  color: white;
  padding: 0.75rem;
  font-weight: 600;
}

.nft-content, .sub-content {
  padding: 1rem;
}

.nft-item, .sub-item {
  margin-bottom: 0.5rem;
}

.nft-actions {
  margin-top: 1rem;
}

.check-sub-btn {
  width: 100%;
  background-color: #2563eb;
}

.sub-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.single-sub-result {
  background-color: #f1f5f9;
  padding: 1.5rem;
  border-radius: 8px;
}

.status {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-weight: 600;
}

.status.active {
  background-color: #d1fae5;
  color: #10b981;
}

.no-subscription {
  text-align: center;
  padding: 1.5rem;
}

.purchase-now-btn {
  margin-top: 1rem;
  background-color: #f59e0b;
}

.purchase-now-btn:hover {
  background-color: #d97706;
}

.wallet-prompt {
  text-align: center;
  padding: 4rem 2rem;
  background-color: #f1f5f9;
  border-radius: 12px;
  margin-top: 2rem;
}

.wallet-prompt p {
  font-size: 1.25rem;
  color: #6c757d;
}

@media (max-width: 768px) {
  .solana-program-view {
    padding: 1rem;
  }

  .query-actions {
    flex-direction: column;
  }
  
  .nft-grid, .sub-list {
    grid-template-columns: 1fr;
  }
}
</style> 