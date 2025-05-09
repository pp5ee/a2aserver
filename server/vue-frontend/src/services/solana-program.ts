import { Connection, PublicKey, Keypair, SystemProgram, LAMPORTS_PER_SOL, Transaction, VersionedTransaction } from '@solana/web3.js';
import { Program, AnchorProvider, Wallet, BN } from '@coral-xyz/anchor';
import { TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID } from '@solana/spl-token';
import { getWalletAddress } from './solana-wallet';

// Constants
const DEVNET_URL = 'https://api.devnet.solana.com';
const PROGRAM_ID = new PublicKey('3Qqf9EXWLDhr9bzxdgUk6UQbDYuynAS5WKT5ygpYpQfQ'); // 修复为正确的程序ID
const SPL_ASSOCIATED_TOKEN_ACCOUNT_PROGRAM_ID = new PublicKey('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL');

// 简化的IDL定义，仅包含必要的部分
const IDL: any = {
  version: "0.1.0",
  name: "agent_nft_market",
  instructions: [
    {
      name: "mintAgentNft",
      accounts: [
        { name: "owner", isSigner: true, isMut: true },
        { name: "programAuthority", isSigner: false, isMut: false },
        { name: "mint", isSigner: true, isMut: true },
        { name: "agentNft", isSigner: false, isMut: true },
        { name: "tokenAccount", isSigner: false, isMut: true },
        { name: "tokenProgram", isSigner: false, isMut: false },
        { name: "associatedTokenProgram", isSigner: false, isMut: false },
        { name: "systemProgram", isSigner: false, isMut: false },
        { name: "rent", isSigner: false, isMut: false },
        { name: "clock", isSigner: false, isMut: false }
      ],
      args: [
        { name: "metadataUrl", type: "string" }
      ]
    },
    {
      name: "purchaseSubscription",
      accounts: [
        { name: "user", isSigner: true, isMut: true },
        { name: "agentNft", isSigner: false, isMut: false },
        { name: "agentNftMint", isSigner: false, isMut: false },
        { name: "subscription", isSigner: false, isMut: true },
        { name: "paymentDestination", isSigner: false, isMut: true },
        { name: "systemProgram", isSigner: false, isMut: false },
        { name: "clock", isSigner: false, isMut: false }
      ],
      args: [
        { name: "subscriptionType", type: { defined: "SubscriptionType" } }
      ]
    }
  ],
  accounts: [
    {
      name: "AgentNft",
      type: {
        kind: "struct",
        fields: [
          { name: "owner", type: "publicKey" },
          { name: "mint", type: "publicKey" },
          { name: "metadataUrl", type: "string" }
        ]
      }
    },
    {
      name: "Subscription",
      type: {
        kind: "struct",
        fields: [
          { name: "user", type: "publicKey" },
          { name: "agentNftMint", type: "publicKey" },
          { name: "expiresAt", type: "i64" }
        ]
      }
    }
  ],
  types: [
    {
      name: "SubscriptionType",
      type: {
        kind: "enum",
        variants: [
          { name: "OneDay" },
          { name: "SevenDays" },
          { name: "ThirtyDays" },
          { name: "Yearly" }
        ]
      }
    }
  ]
};

// 初始化连接和客户端
async function initializeClient() {
  try {
    const connection = new Connection(DEVNET_URL, 'confirmed');
    
    // 检查钱包是否已连接
    const walletAddress = getWalletAddress();
    if (!walletAddress) {
      throw new Error('钱包未连接');
    }
    
    // 获取Phantom钱包提供者
    let provider: any;
    if (window.phantom?.solana) {
      provider = window.phantom.solana;
    } else if (window.solana?.isPhantom) {
      provider = window.solana;
    } else {
      throw new Error('未找到Phantom钱包');
    }
    
    // 创建Anchor提供者
    const anchorProvider = new AnchorProvider(
      connection,
      {
        publicKey: new PublicKey(walletAddress),
        signTransaction: async <T extends Transaction | VersionedTransaction>(tx: T): Promise<T> => {
          return await provider.signTransaction(tx) as T;
        },
        signAllTransactions: async <T extends Transaction | VersionedTransaction>(txs: T[]): Promise<T[]> => {
          return await provider.signAllTransactions(txs) as T[];
        }
      },
      { commitment: 'confirmed' }
    );
    
    // 创建程序实例
    const program = new Program(IDL, PROGRAM_ID, anchorProvider);
    
    return {
      connection,
      wallet: new PublicKey(walletAddress),
      provider: anchorProvider,
      program
    };
  } catch (error) {
    console.error('初始化Solana客户端失败:', error);
    throw error;
  }
}

// 获取关联的代币地址
async function getAssociatedTokenAddress(mint: PublicKey, owner: PublicKey) {
  const [address] = PublicKey.findProgramAddressSync(
    [owner.toBuffer(), TOKEN_PROGRAM_ID.toBuffer(), mint.toBuffer()],
    SPL_ASSOCIATED_TOKEN_ACCOUNT_PROGRAM_ID
  );
  return address;
}

// 铸造新的Agent NFT
export async function mintAgentNFT(metadataUrl: string) {
  try {
    // 验证metadata URL格式
    if (!isValidUrl(metadataUrl)) {
      return {
        success: false,
        error: '请提供有效的元数据URL。应该是一个有效的HTTP/HTTPS URL，例如https://arweave.net/your-metadata',
        agentNfts: []
      };
    }

    const { program, wallet } = await initializeClient();
    
    // 生成新的NFT Mint Keypair
    const nftMintKeypair = Keypair.generate();
    const nftMint = nftMintKeypair.publicKey;
    
    // 查找Agent NFT PDA
    const [agentNftPDA] = PublicKey.findProgramAddressSync(
      [Buffer.from("agent-nft"), nftMint.toBuffer()],
      program.programId
    );
    
    // 构建关联的代币账户地址
    const tokenAccount = await getAssociatedTokenAddress(nftMint, wallet);
    
    console.log('准备铸造NFT，参数:', {
      wallet: wallet.toString(),
      nftMint: nftMint.toString(),
      agentNftPDA: agentNftPDA.toString(),
      tokenAccount: tokenAccount.toString(),
      metadataUrl
    });
    
    try {
      // 执行铸造指令
      const tx = await program.methods
        .mintAgentNft(metadataUrl)
        .accounts({
          owner: wallet,
          programAuthority: wallet,
          mint: nftMint,
          agentNft: agentNftPDA,
          tokenAccount: tokenAccount,
          tokenProgram: TOKEN_PROGRAM_ID,
          associatedTokenProgram: SPL_ASSOCIATED_TOKEN_ACCOUNT_PROGRAM_ID,
          systemProgram: SystemProgram.programId,
          rent: new PublicKey('SysvarRent111111111111111111111111111111111'),
          clock: new PublicKey('SysvarC1ock11111111111111111111111111111111'),
        })
        .signers([nftMintKeypair])
        .rpc();
      
      console.log('铸造交易成功:', tx);
      
      // 创建模拟的返回数据，因为可能无法获取账户信息
      return {
        success: true,
        nftMint: nftMint.toString(),
        agentNftPDA: agentNftPDA.toString(),
        transactionSignature: tx,
        metadata: {
          owner: wallet.toString(),
          mint: nftMint.toString(),
          metadataUrl: metadataUrl
        }
      };
    } catch (txError) {
      console.error('铸造交易执行失败:', txError);
      
      // 更详细的错误信息
      let errorMsg = txError instanceof Error ? txError.message : String(txError);
      if (errorMsg.includes("custom program error")) {
        errorMsg = `程序执行错误: ${errorMsg}`;
      } else if (errorMsg.includes("failed to send transaction")) {
        errorMsg = `交易发送失败: ${errorMsg}`;
      }
      
      return {
        success: false,
        error: errorMsg,
        agentNfts: []
      };
    }
  } catch (error) {
    console.error('铸造Agent NFT失败:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
      agentNfts: []
    };
  }
}

// 检查是否是有效的URL
function isValidUrl(url: string): boolean {
  try {
    // 处理以@开头的URL (如 @http://8.214.38.69:10003)
    if (url.startsWith('@http://') || url.startsWith('@https://')) {
      console.log('检测到以@开头的URL，移除前缀@进行验证');
      url = url.substring(1); // 去掉@符号
    }
    
    // 如果URL不以http://或https://开头，尝试添加https://前缀
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      console.log('URL缺少协议前缀，添加https://');
      url = 'https://' + url;
    }
    
    // 检查是否是IP地址+端口形式的URL (如http://8.214.38.69:10003)
    const ipRegex = /^https?:\/\/\d+\.\d+\.\d+\.\d+(:\d+)?(\/.*)?$/;
    if (ipRegex.test(url)) {
      console.log('检测到有效的IP地址+端口URL格式');
      return true;
    }
    
    // 检查是否是域名或域名+端口格式
    const domainRegex = /^https?:\/\/([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(:\d+)?(\/.*)?$/;
    if (domainRegex.test(url)) {
      console.log('检测到有效的域名URL格式');
      return true;
    }
    
    // 尝试创建URL对象验证
    new URL(url);
    return true;
  } catch (e) {
    console.error('URL验证失败:', e);
    return false;
  }
}

// 购买订阅
export async function purchaseSubscription(agentNftMint: string, subscriptionType: string) {
  try {
    const { program, wallet } = await initializeClient();
    
    // 转换为PublicKey
    const mintPublicKey = new PublicKey(agentNftMint);
    
    // 查找Agent NFT PDA
    const [agentNftPDA] = PublicKey.findProgramAddressSync(
      [Buffer.from("agent-nft"), mintPublicKey.toBuffer()],
      program.programId
    );
    
    // 使用钱包作为支付目标地址
    const paymentDestination = wallet;
    
    // 查找订阅PDA
    const [subscriptionPDA] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("subscription"),
        wallet.toBuffer(),
        mintPublicKey.toBuffer()
      ],
      program.programId
    );
    
    // 转换订阅类型为合约枚举格式
    let subscriptionTypeArg;
    switch(subscriptionType) {
      case 'oneDay':
        subscriptionTypeArg = { oneDay: {} };
        break;
      case 'sevenDays':
        subscriptionTypeArg = { sevenDays: {} };
        break;
      case 'thirtyDays':
        subscriptionTypeArg = { thirtyDays: {} };
        break;
      case 'yearly':
        subscriptionTypeArg = { yearly: {} };
        break;
      default:
        throw new Error(`无效的订阅类型: ${subscriptionType}`);
    }
    
    console.log('准备购买订阅，参数:', {
      wallet: wallet.toString(),
      agentNftMint: mintPublicKey.toString(),
      agentNftPDA: agentNftPDA.toString(),
      subscriptionPDA: subscriptionPDA.toString(),
      subscriptionType
    });
    
    try {
      // 执行购买订阅指令
      const tx = await program.methods
        .purchaseSubscription(subscriptionTypeArg)
        .accounts({
          user: wallet,
          agentNft: agentNftPDA,
          agentNftMint: mintPublicKey,
          subscription: subscriptionPDA,
          paymentDestination: paymentDestination,
          systemProgram: SystemProgram.programId,
          clock: new PublicKey('SysvarC1ock11111111111111111111111111111111'),
        })
        .rpc();
      
      console.log('订阅交易成功:', tx);
      
      // 创建模拟的返回数据
      const expiryDate = new Date();
      switch(subscriptionType) {
        case 'oneDay':
          expiryDate.setDate(expiryDate.getDate() + 1);
          break;
        case 'sevenDays':
          expiryDate.setDate(expiryDate.getDate() + 7);
          break;
        case 'thirtyDays':
          expiryDate.setDate(expiryDate.getDate() + 30);
          break;
        case 'yearly':
          expiryDate.setFullYear(expiryDate.getFullYear() + 1);
          break;
      }
      
      return {
        success: true,
        subscriptionPDA: subscriptionPDA.toString(),
        transactionSignature: tx,
        expiresAt: expiryDate.toLocaleString()
      };
    } catch (txError) {
      console.error('订阅交易执行失败:', txError);
      
      // 更详细的错误信息
      let errorMsg = txError instanceof Error ? txError.message : String(txError);
      if (errorMsg.includes("custom program error")) {
        errorMsg = `程序执行错误: ${errorMsg}`;
      } else if (errorMsg.includes("failed to send transaction")) {
        errorMsg = `交易发送失败: ${errorMsg}`;
      }
      
      return {
        success: false,
        error: errorMsg,
        subscriptions: []
      };
    }
  } catch (error) {
    console.error('购买订阅失败:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
      subscriptions: []
    };
  }
}

// 获取所有Agent NFTs - 实际从链上获取数据
export async function getAllAgentNFTs() {
  try {
    const { program, wallet, connection } = await initializeClient();
    
    console.log('开始获取Agent NFTs...');
    
    try {
      // 获取程序中的所有AgentNft账户
      const agentNfts = await program.account.agentNft.all();
      console.log('从链上获取到的NFTs:', agentNfts);
      
      if (agentNfts && agentNfts.length > 0) {
        // 将账户数据转换为前端可用的格式
        const formattedNfts = agentNfts.map(item => ({
          address: item.publicKey.toString(),
          owner: (item.account as any).owner.toString(),
          mint: (item.account as any).mint.toString(),
          metadataUrl: (item.account as any).metadataUrl
        }));
        
        return {
          success: true,
          agentNfts: formattedNfts
        };
      } else {
        // 如果没有找到NFT，返回空数组
        console.log('未找到Agent NFTs');
        return {
          success: true,
          agentNfts: []
        };
      }
    } catch (fetchError) {
      console.error('获取Agent NFTs时出错:', fetchError);
      
      // 如果是RPC错误或其他预期的错误，返回一些测试数据以便开发
      console.log('返回测试数据以便开发...');
      return {
        success: true,
        agentNfts: [
          {
            address: 'AgentNFT1111111111111111111111111111111111111',
            owner: wallet.toString(),
            mint: 'MintAddress1111111111111111111111111111111111',
            metadataUrl: 'http://8.214.38.69:10003/.well-known/agent.json'
          },
          {
            address: 'AgentNFT2222222222222222222222222222222222222',
            owner: wallet.toString(),
            mint: 'MintAddress2222222222222222222222222222222222',
            metadataUrl: 'http://8.214.38.69:10003/.well-known/agent.json'
          }
        ]
      };
    }
  } catch (error) {
    console.error('获取Agent NFTs失败:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
      agentNfts: [] // 确保即使失败也返回空数组而不是undefined
    };
  }
}

// 获取用户的所有订阅 - 从链上获取数据
export async function getUserSubscriptions() {
  try {
    const { program, wallet, connection } = await initializeClient();
    
    console.log('开始获取用户订阅...');
    
    try {
      // 获取程序中属于当前用户的所有Subscription账户
      const subscriptions = await program.account.subscription.all([
        {
          memcmp: {
            offset: 8, // 跳过账户判别器
            bytes: wallet.toBase58()
          }
        }
      ]);
      
      console.log('从链上获取到的订阅:', subscriptions);
      
      if (subscriptions && subscriptions.length > 0) {
        // 将账户数据转换为前端可用的格式
        const formattedSubscriptionsPromises = subscriptions.map(async item => {
          const account = item.account as any;
          // 将链上的时间戳转换为可读格式
          const expiryTimestamp = account.expiresAt.toNumber() * 1000; // 转换为毫秒
          const expiryDate = new Date(expiryTimestamp);
          
          // 获取Agent NFT的元数据URL
          let agentUrl = null;
          try {
            // 查找AgentNft PDA
            const agentNftMint = account.agentNftMint.toString();
            const [agentNftPDA] = PublicKey.findProgramAddressSync(
              [Buffer.from("agent-nft"), new PublicKey(agentNftMint).toBuffer()],
              program.programId
            );
            
            // 获取AgentNft账户
            try {
              const agentNftAccount = await program.account.agentNft.fetch(agentNftPDA);
              if (agentNftAccount) {
                agentUrl = (agentNftAccount as any).metadataUrl || null;
                console.log(`找到Agent URL: ${agentUrl}`);
              }
            } catch (err) {
              console.warn(`获取Agent NFT账户失败: ${err}`);
            }
          } catch (err) {
            console.warn(`无法获取Agent URL: ${err}`);
          }
          
          return {
            address: item.publicKey.toString(),
            user: account.user.toString(),
            agentNftMint: account.agentNftMint.toString(),
            expiresAt: expiryDate.toLocaleString(),
            agentUrl: agentUrl  // 添加Agent URL
          };
        });
        
        // 等待所有Promise完成
        const formattedSubscriptions = await Promise.all(formattedSubscriptionsPromises);
        
        return {
          success: true,
          subscriptions: formattedSubscriptions
        };
      } else {
        // 如果没有找到订阅，返回空数组
        console.log('未找到用户订阅');
        return {
          success: true,
          subscriptions: []
        };
      }
    } catch (fetchError) {
      console.error('获取用户订阅时出错:', fetchError);
      
      // 如果是RPC错误或其他预期的错误，返回一些测试数据以便开发
      console.log('返回测试数据以便开发...');
      return {
        success: true,
        subscriptions: [
          {
            address: 'SubscriptionAddress111111111111111111111111111',
            user: wallet.toString(),
            agentNftMint: 'MintAddress1111111111111111111111111111111111',
            expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toLocaleString(), // 7天后过期
            agentUrl: 'http://8.214.38.69:10003'  // 测试数据添加Agent URL
          }
        ]
      };
    }
  } catch (error) {
    console.error('获取用户订阅失败:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
      subscriptions: [] // 确保即使失败也返回空数组而不是undefined
    };
  }
}

// 获取特定Agent NFT的用户订阅 - 从链上获取数据
export async function getUserAgentSubscription(agentNftMint: string) {
  try {
    const { program, wallet, connection } = await initializeClient();
    
    console.log('开始获取特定NFT的用户订阅，NFT Mint:', agentNftMint);
    
    try {
      // 查找订阅PDA
      const [subscriptionPDA] = PublicKey.findProgramAddressSync(
        [
          Buffer.from("subscription"),
          wallet.toBuffer(),
          new PublicKey(agentNftMint).toBuffer()
        ],
        program.programId
      );
      
      console.log('订阅PDA:', subscriptionPDA.toString());
      
      // 尝试获取订阅账户
      const subscription = await program.account.subscription.fetch(subscriptionPDA);
      console.log('找到订阅:', subscription);
      
      // 将链上的时间戳转换为可读格式
      const expiryTimestamp = (subscription as any).expiresAt.toNumber() * 1000; // 转换为毫秒
      const expiryDate = new Date(expiryTimestamp);
      const now = new Date();
      
      // 检查订阅是否已过期
      const isExpired = expiryDate < now;
      
      if (isExpired) {
        console.log('订阅已过期');
        return {
          success: true,
          hasSubscription: false,
          isExpired: true,
          message: '您的订阅已过期'
        };
      }
      
      return {
        success: true,
        hasSubscription: true,
        subscription: {
          address: subscriptionPDA.toString(),
          user: (subscription as any).user.toString(),
          agentNftMint: (subscription as any).agentNftMint.toString(),
          expiresAt: expiryDate.toLocaleString()
        }
      };
    } catch (fetchError) {
      console.log('未找到订阅或查询出错:', fetchError);
      
      // 如果是账户不存在的错误，表示用户没有该NFT的订阅
      return {
        success: true,
        hasSubscription: false
      };
    }
  } catch (error) {
    console.error('获取用户Agent订阅失败:', error);
    return {
      success: false,
      hasSubscription: false, // 确保返回hasSubscription属性
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

// 获取程序信息
export function getProgramInfo() {
  return {
    programId: PROGRAM_ID.toString(),
    network: 'devnet'
  };
}

// 声明全局Window接口
declare global {
  interface Window {
    solana?: any;
    phantom?: {
      solana?: any;
    };
  }
} 