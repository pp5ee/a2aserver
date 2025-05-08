<template>
  <div class="nft-metadata-viewer">
    <h3>NFT Metadata</h3>
    
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>Loading metadata...</span>
    </div>
    
    <div v-else-if="error" class="error-state">
      <div class="error-icon">!</div>
      <div class="error-message">
        <strong>Error loading metadata</strong>
        <p>{{ error }}</p>
        <div class="metadata-url">
          <span class="label">URL:</span>
          <span class="value">{{ metadataUrl }}</span>
        </div>
        <button @click="retryLoading" class="retry-button">Retry</button>
      </div>
    </div>
    
    <div v-else-if="metadata" class="metadata-content">
      <div class="metadata-header">
        <div v-if="metadata.image" class="metadata-image">
          <img :src="metadata.image" alt="NFT Image" />
        </div>
        <div class="metadata-info">
          <h4>{{ metadata.name || 'Unnamed NFT' }}</h4>
          <p class="description">{{ metadata.description || 'No description' }}</p>
        </div>
      </div>
      
      <div class="metadata-details">
        <div class="metadata-url">
          <span class="label">Source URL:</span>
          <span class="value">{{ metadataUrl }}</span>
        </div>
        
        <div v-if="metadata.attributes && metadata.attributes.length" class="metadata-attributes">
          <h5>Attributes</h5>
          <div class="attributes-grid">
            <div v-for="(attr, index) in metadata.attributes" :key="index" class="attribute-item">
              <span class="attr-trait">{{ attr.trait_type || 'Property' }}</span>
              <span class="attr-value">{{ attr.value }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <div v-else class="empty-state">
      <p>No metadata available</p>
      <div class="metadata-url">
        <span class="label">URL:</span>
        <span class="value">{{ metadataUrl || 'Not specified' }}</span>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, watch, onMounted } from 'vue';
import { fetchMetadataViaProxy } from '@/services/metadata-proxy';

export default defineComponent({
  name: 'NftMetadataViewer',
  
  props: {
    metadataUrl: {
      type: String,
      required: true
    }
  },
  
  setup(props) {
    const metadata = ref<any>(null);
    const loading = ref(false);
    const error = ref<string | null>(null);
    
    // 加载元数据
    const loadMetadata = async () => {
      if (!props.metadataUrl) {
        error.value = 'No metadata URL provided';
        return;
      }
      
      loading.value = true;
      error.value = null;
      
      try {
        // 使用代理服务获取元数据
        console.log('通过代理获取元数据:', props.metadataUrl);
        const data = await fetchMetadataViaProxy(props.metadataUrl);
        metadata.value = data;
        console.log('成功加载元数据:', data);
      } catch (err) {
        console.error('加载元数据时出错:', err);
        
        // 错误处理
        let errorMessage = err instanceof Error ? err.message : String(err);
        if (errorMessage.includes('CORS') || 
            errorMessage.includes('cross-origin') || 
            errorMessage.includes('Cross-Origin')) {
          errorMessage = `CORS错误: 服务器 ${props.metadataUrl} 不允许来自此源的请求。
          请确保服务器配置了正确的CORS头。`;
        }
        
        error.value = errorMessage;
        metadata.value = null;
      } finally {
        loading.value = false;
      }
    };
    
    // 重试加载
    const retryLoading = () => {
      loadMetadata();
    };
    
    // 监听URL变化
    watch(() => props.metadataUrl, (newUrl) => {
      if (newUrl) {
        loadMetadata();
      } else {
        metadata.value = null;
        error.value = null;
      }
    });
    
    // 组件挂载时加载
    onMounted(() => {
      if (props.metadataUrl) {
        loadMetadata();
      }
    });
    
    return {
      metadata,
      loading,
      error,
      retryLoading
    };
  }
});
</script>

<style scoped>
.nft-metadata-viewer {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
  background-color: #f9f9f9;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid rgba(81, 45, 168, 0.3);
  border-radius: 50%;
  border-top-color: #512da8;
  animation: spin 1s ease-in-out infinite;
  margin-right: 10px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-state {
  display: flex;
  padding: 16px;
  background-color: rgba(244, 67, 54, 0.1);
  border-radius: 4px;
}

.error-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: #f44336;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  margin-right: 16px;
}

.error-message {
  flex: 1;
}

.retry-button {
  background-color: #f44336;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  margin-top: 10px;
}

.retry-button:hover {
  background-color: #d32f2f;
}

.metadata-content {
  display: flex;
  flex-direction: column;
}

.metadata-header {
  display: flex;
  margin-bottom: 16px;
}

.metadata-image {
  width: 120px;
  height: 120px;
  border-radius: 8px;
  overflow: hidden;
  margin-right: 16px;
  background-color: #e0e0e0;
}

.metadata-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.metadata-info {
  flex: 1;
}

.metadata-info h4 {
  margin: 0 0 8px 0;
  color: #333;
}

.description {
  color: #666;
  font-size: 14px;
  margin: 0;
}

.metadata-details {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e0e0e0;
}

.metadata-url {
  display: flex;
  margin-bottom: 10px;
  font-size: 14px;
  word-break: break-all;
}

.label {
  font-weight: 500;
  color: #666;
  margin-right: 8px;
  min-width: 80px;
}

.value {
  color: #333;
}

.metadata-attributes {
  margin-top: 16px;
}

.metadata-attributes h5 {
  margin: 0 0 10px 0;
  color: #333;
}

.attributes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}

.attribute-item {
  background-color: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
}

.attr-trait {
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
}

.attr-value {
  font-weight: 500;
  color: #333;
}

.empty-state {
  text-align: center;
  padding: 20px;
  color: #666;
}
</style> 