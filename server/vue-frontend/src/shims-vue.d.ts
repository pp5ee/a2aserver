/* eslint-disable */
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// 添加模块声明
declare module '@/components/PhantomWallet.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module '@/components/NftMetadataViewer.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module '@/services/solana-wallet' {
  export function isWalletConnected(): boolean;
  export function getWalletAddress(): string | null;
  export function connectAndSign(expiryDuration?: number | string): Promise<{ 
    success: boolean; 
    address?: string;
    nonce?: string;
    signature?: string;
    error?: string;
  }>;
  export function disconnectWallet(): void;
  export function getRemainingValidTime(): number;
  export function formatDuration(duration: number): string;
  export function getSignatureExpiryTime(): number | null;
  export function isSignatureExpired(): boolean;
  export const EXPIRY_PRESETS: {
    DAY_7: number;
    DAY_30: number;
    DAY_90: number;
  };
}

declare module '@/services/solana-program' {
  export function mintAgentNFT(metadataUrl: string): Promise<any>;
  export function purchaseSubscription(agentNftMint: string, subscriptionType: string): Promise<any>;
  export function getAllAgentNFTs(): Promise<any>;
  export function getUserSubscriptions(): Promise<any>;
  export function getUserAgentSubscription(agentNftMint: string): Promise<any>;
  export function getProgramInfo(): { programId: string; network: string };
}

declare module '@/services/metadata-proxy' {
  export function fetchMetadataViaProxy(originalUrl: string): Promise<any>;
} 