const { SystemProgram,Connection, Keypair, PublicKey, LAMPORTS_PER_SOL, sendAndConfirmTransaction, SYSVAR_CLOCK_PUBKEY } = require('@solana/web3.js');
const { Program, AnchorProvider, Wallet, BN } = require('@coral-xyz/anchor');

const { TOKEN_PROGRAM_ID } = require('@solana/spl-token');
const fs = require('fs');
require('dotenv').config();

// Load IDL from file
// const idlFile = './agent_nft_market.json';
// const idl = JSON.parse(fs.readFileSync(idlFile, 'utf8'));
const idl = require("./agent_nft_market.json");
console.log("Program ID:", idl.address);
// Constants
const PROGRAM_ID = new PublicKey(process.env.PROGRAM_ID || idl.address);
const DEVNET_URL = 'https://api.devnet.solana.com';
const ASSOCIATED_TOKEN_PROGRAM_ID = new PublicKey('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL');

// Initialize connection and wallet
async function initializeClient() {
  const connection = new Connection(DEVNET_URL, 'confirmed');
  
  // Load program authority from private key
  const programAuthorityKeypair = Keypair.fromSecretKey(
    Buffer.from(JSON.parse(process.env.PROGRAM_AUTHORITY_PRIVATE_KEY))
  );

  // Load wallet from private key
  const walletKeypair = Keypair.fromSecretKey(
    Buffer.from(JSON.parse(process.env.WALLET_PRIVATE_KEY))
  );
  
  const wallet = new Wallet(walletKeypair);
  const programAuthorityWallet = new Wallet(programAuthorityKeypair);
  const provider = new AnchorProvider(
    connection, 
    wallet,
    { commitment: 'confirmed' }
  );
  
  const program = new Program(idl, provider);
  
  console.log("wallet public key:", walletKeypair.publicKey.toBase58());
  console.log("program authority public key:", programAuthorityKeypair.publicKey.toBase58());
  return { 
    connection, 
    wallet, 
    walletPublicKey: walletKeypair.publicKey, 
    provider, 
    program ,
    programAuthorityWallet
  };
}

// Helper function to get associated token address
async function getAssociatedTokenAddress(mint, owner) {
  const [address] = PublicKey.findProgramAddressSync(
    [owner.toBuffer(), TOKEN_PROGRAM_ID.toBuffer(), mint.toBuffer()],
    ASSOCIATED_TOKEN_PROGRAM_ID
  );
  return address;
}

// Initialize fee collector
async function initializeFeeCollector(program, payerWallet) {
  console.log("Initializing fee collector...");
  
  // Calculate the PDA for fee collector
  const [feeCollectorPDA, feeCollectorBump] = PublicKey.findProgramAddressSync(
    [Buffer.from("fee_account")],
    program.programId
  );
  
  console.log(`Fee Collector PDA: ${feeCollectorPDA.toBase58()}`);
  console.log(`Fee Collector Bump: ${feeCollectorBump}`);
  
  try {
    const tx = await program.methods
      .initializeFeeCollector()
      .accounts({
        user: payerWallet.publicKey,
        feeCollector: feeCollectorPDA,
        systemProgram: SystemProgram.programId,
      })
      .signers([payerWallet.payer])
      .rpc();
    
    console.log(`Fee collector initialized! Transaction signature: ${tx}`);
    
    // Get fee collector balance
    const balance = await program.provider.connection.getBalance(feeCollectorPDA);
    console.log(`Fee collector balance: ${balance} lamports`);
    
    return { feeCollectorPDA, feeCollectorBump };
  } catch (error) {
    console.error("Error initializing fee collector:", error);
    throw error;
  }
}

// Mint a new Agent NFT
async function mintAgentNFT(program, owner, programAuthorityWallet, metadataUrl) {
  console.log(`Minting a new Agent NFT for ${owner.publicKey.toBase58()}`);
  console.log(`Metadata URL: ${metadataUrl}`);
  
  // Generate a new keypair for the NFT mint
  const nftMintKeypair = Keypair.generate();
  const nftMint = nftMintKeypair.publicKey;
  
  console.log(`NFT Mint: ${nftMint.toBase58()}`);
  console.log(`Program ID: ${program.programId}`);
  
  // Find the AgentNft PDA
  const [agentNftPDA] = PublicKey.findProgramAddressSync(
    [Buffer.from("agent-nft"), nftMint.toBuffer()],
    program.programId
  );
  
  console.log(`Agent NFT PDA: ${agentNftPDA.toBase58()}`);
  
  try {
    // Perform the mint_agent_nft instruction
    const tx = await program.methods
      .mintAgentNft(metadataUrl)
      .accounts({
        owner: owner.publicKey,
        programAuthority: programAuthorityWallet.publicKey,
        mint: nftMint,
        agentNft: agentNftPDA,
        tokenAccount: await getAssociatedTokenAddress(
          nftMint,
          programAuthorityWallet.publicKey
        ),
        tokenProgram: TOKEN_PROGRAM_ID,
        associatedTokenProgram: ASSOCIATED_TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: new PublicKey('SysvarRent111111111111111111111111111111111'),
        clock: SYSVAR_CLOCK_PUBKEY,
      })
      .signers([nftMintKeypair, programAuthorityWallet.payer])
      .rpc();
    
    console.log(`NFT minted successfully! Transaction signature: ${tx}`);
    
    // Fetch the Agent NFT account to verify
    const agentNftAccount = await program.account.agentNft.fetch(agentNftPDA);
    
    console.log(`Agent NFT Account:
      - Owner: ${agentNftAccount.owner.toBase58()}
      - Mint: ${agentNftAccount.mint.toBase58()}
      - Metadata URL: ${agentNftAccount.metadataUrl}
    `);
    
    return { 
      nftMint,
      agentNftPDA,
      transactionSignature: tx 
    };
  } catch (error) {
    console.error("Error minting Agent NFT:", error);
    throw error;
  }
}

// Purchase a subscription
async function purchaseSubscription(program, user, agentNftMint, subscriptionType, feeCollectorPDA) {
  console.log(`Purchasing a ${subscriptionType} subscription for ${user.publicKey.toBase58()}`);
  
  // Find the AgentNft PDA
  const [agentNftPDA] = PublicKey.findProgramAddressSync(
    [Buffer.from("agent-nft"), agentNftMint.toBuffer()],
    program.programId
  );
  console.log(`Agent NFT PDA: ${agentNftPDA.toBase58()}`);
  
  // Find the Subscription PDA
  const [subscriptionPDA] = PublicKey.findProgramAddressSync(
    [
      Buffer.from("subscription"),
      user.publicKey.toBuffer(),
      agentNftMint.toBuffer(),
    ],
    program.programId
  );
  
  console.log(`Subscription PDA: ${subscriptionPDA.toBase58()}`);
  
  try {
    // Get the Agent NFT account to determine payment destination
    const agentNftAccount = await program.account.agentNft.fetch(agentNftPDA);
    const paymentDestination = agentNftAccount.owner;
    
    console.log(`Payment Destination: ${paymentDestination.toBase58()}`);
    console.log(`Fee Collector PDA: ${feeCollectorPDA.toBase58()}`);
    
    // Convert subscription type to the contract's enum format
    // Options: { oneDay: {} }, { sevenDays: {} }, { thirtyDays: {} }, { year: {} }
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
        subscriptionTypeArg = { year: {} };
        break;
      default:
        throw new Error(`Invalid subscription type: ${subscriptionType}`);
    }
    
    // Purchase the subscription
    const tx = await program.methods
      .purchaseSubscription(subscriptionTypeArg)
      .accounts({
        user: user.publicKey,
        agentNft: agentNftPDA,
        agentNftMint: agentNftMint,
        subscription: subscriptionPDA,
        paymentDestination: paymentDestination,
        feeCollector: feeCollectorPDA,
        systemProgram: SystemProgram.programId,
        clock: SYSVAR_CLOCK_PUBKEY,
      })
      .signers([user.payer])
      .rpc();
    
    console.log(`Subscription purchased successfully! Transaction signature: ${tx}`);
    
    // Fetch the subscription account to verify
    const subscriptionAccount = await program.account.subscription.fetch(subscriptionPDA);
    
    const expiresAt = new Date(subscriptionAccount.expiresAt.toNumber() * 1000).toLocaleString();
    console.log(`Subscription Account:
      - User: ${subscriptionAccount.user.toBase58()}
      - Agent NFT Mint: ${subscriptionAccount.agentNftMint.toBase58()}
      - Expires At: ${expiresAt}
    `);
    
    return {
      subscriptionPDA,
      transactionSignature: tx,
      expiresAt: subscriptionAccount.expiresAt
    };
  } catch (error) {
    console.error(`Error purchasing ${subscriptionType} subscription:`, error);
    throw error;
  }
}

// Withdraw fees
async function withdrawFees(program, authority, withdrawDestination) {
  console.log(`Withdrawing fees to ${withdrawDestination.toBase58()}...`);
  
  // Calculate the PDA for fee collector
  const [feeCollectorPDA] = PublicKey.findProgramAddressSync(
    [Buffer.from("fee_account")],
    program.programId
  );
  
  console.log(`Fee Collector PDA: ${feeCollectorPDA.toBase58()}`);
  
  try {
    // Get initial balances
    const initialFeeCollectorBalance = await program.provider.connection.getBalance(feeCollectorPDA);
    const initialDestinationBalance = await program.provider.connection.getBalance(withdrawDestination);
    
    console.log(`Initial Fee Collector Balance: ${initialFeeCollectorBalance} lamports`);
    console.log(`Initial Destination Balance: ${initialDestinationBalance} lamports`);
    
    if (initialFeeCollectorBalance === 0) {
      console.log("Fee collector has no funds to withdraw");
      return { success: false, reason: "No funds to withdraw" };
    }
    
    // Perform the withdrawal
    const tx = await program.methods
      .withdrawFees()
      .accounts({
        authority: authority.publicKey,
        feeCollector: feeCollectorPDA,
        withdrawDestination: withdrawDestination,
        systemProgram: SystemProgram.programId,
      })
      .signers([authority.payer])
      .rpc();
    
    console.log(`Fees withdrawn successfully! Transaction signature: ${tx}`);
    
    // Check final balances
    const finalFeeCollectorBalance = await program.provider.connection.getBalance(feeCollectorPDA);
    const finalDestinationBalance = await program.provider.connection.getBalance(withdrawDestination);
    
    console.log(`Final Fee Collector Balance: ${finalFeeCollectorBalance} lamports`);
    console.log(`Final Destination Balance: ${finalDestinationBalance} lamports`);
    console.log(`Amount transferred: ${finalDestinationBalance - initialDestinationBalance} lamports`);
    
    return {
      success: true,
      transactionSignature: tx,
      amountWithdrawn: finalDestinationBalance - initialDestinationBalance
    };
  } catch (error) {
    console.error("Error withdrawing fees:", error);
    throw error;
  }
}

// Get all Agent NFTs
async function getAllAgentNFTs(program) {
  console.log("Fetching all Agent NFTs...");
  
  try {
    const agentNfts = await program.account.agentNft.all();
    
    console.log(`Found ${agentNfts.length} Agent NFTs`);
    
    agentNfts.forEach((nft, index) => {
      console.log(`Agent NFT #${index + 1}:`);
      console.log(`  - Address: ${nft.publicKey.toBase58()}`);
      console.log(`  - Owner: ${nft.account.owner.toBase58()}`);
      console.log(`  - Mint: ${nft.account.mint.toBase58()}`);
      console.log(`  - Metadata URL: ${nft.account.metadataUrl}`);
    });
    
    return agentNfts;
  } catch (error) {
    console.error("Error fetching Agent NFTs:", error);
    throw error;
  }
}

// Get all user subscriptions
async function getUserSubscriptions(program, userPublicKey) {
  console.log(`Fetching subscriptions for user: ${userPublicKey.toBase58()}`);
  
  try {
    // Get all program accounts that match Subscription's discriminator with user filter
    const subscriptionAccounts = await program.account.subscription.all([
      {
        memcmp: {
          offset: 8, // Skip discriminator (8 bytes)
          bytes: userPublicKey.toBase58(), // Filter by user pubkey
        },
      },
    ]);
    
    console.log(`Found ${subscriptionAccounts.length} subscriptions`);
    
    // Fetch detailed information for each subscription
    const subscriptionInfos = await Promise.all(
      subscriptionAccounts.map(async (subscriptionAccount, index) => {
        const subscription = subscriptionAccount.account;
        
        // Get the AgentNft account for this subscription
        const [agentNftPDA] = PublicKey.findProgramAddressSync(
          [Buffer.from("agent-nft"), subscription.agentNftMint.toBuffer()],
          program.programId
        );
        
        // Fetch the AgentNft account data
        const agentNft = await program.account.agentNft.fetch(agentNftPDA);
        
        // Check if subscription is active
        const isActive = subscription.expiresAt.toNumber() > (Date.now() / 1000);
        const expiresAt = new Date(subscription.expiresAt.toNumber() * 1000).toLocaleString();
        
        // Log subscription details
        console.log(`Subscription #${index + 1}:`);
        console.log(`  - Address: ${subscriptionAccount.publicKey.toBase58()}`);
        console.log(`  - Agent NFT Mint: ${subscription.agentNftMint.toBase58()}`);
        console.log(`  - Agent NFT Metadata URL: ${agentNft.metadataUrl}`);
        console.log(`  - Expires At: ${expiresAt}`);
        console.log(`  - Status: ${isActive ? 'Active' : 'Expired'}`);
        
        // Return subscription info with metadata
        return {
          address: subscriptionAccount.publicKey,
          agentNftMint: subscription.agentNftMint,
          agentNftMetadataUrl: agentNft.metadataUrl,
          expiresAt: subscription.expiresAt,
          isActive
        };
      })
    );
    
    return subscriptionInfos;
  } catch (error) {
    console.error("Error getting user subscriptions:", error);
    throw error;
  }
}

// Get subscription for specific agent
async function getUserAgentSubscription(program, userPublicKey, agentNftMint) {
  console.log(`Fetching subscription for user: ${userPublicKey.toBase58()} and Agent NFT: ${agentNftMint.toBase58()}`);
  
  try {
    // Find the AgentNft PDA
    const [agentNftPDA] = PublicKey.findProgramAddressSync(
      [Buffer.from("agent-nft"), agentNftMint.toBuffer()],
      program.programId
    );
    
    // Find the Subscription PDA
    const [subscriptionPDA] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("subscription"),
        userPublicKey.toBuffer(),
        agentNftMint.toBuffer(),
      ],
      program.programId
    );
    
    // Get the user's subscription for the specific Agent NFT
    const subscriptionInfo = await program.methods
      .getUserAgentSubscription()
      .accounts({
        user: userPublicKey,
        agentNftMint: agentNftMint,
        agentNft: agentNftPDA,
        subscription: subscriptionPDA,
      })
      .view({ commitment: 'confirmed' });
    
    // Check if subscription is active
    const isActive = subscriptionInfo.expiresAt.toNumber() > (Date.now() / 1000);
    const expiresAt = new Date(subscriptionInfo.expiresAt.toNumber() * 1000).toLocaleString();
    
    console.log(`Subscription Details:`);
    console.log(`  - Agent NFT Mint: ${subscriptionInfo.agentNftMint.toBase58()}`);
    console.log(`  - Metadata URL: ${subscriptionInfo.metadataUrl}`);
    console.log(`  - Expires At: ${expiresAt}`);
    console.log(`  - Status: ${isActive ? 'Active' : 'Expired'}`);
    
    return {
      ...subscriptionInfo,
      isActive
    };
  } catch (error) {
    if (error.message && error.message.includes("AccountNotInitialized")) {
      console.log("No subscription found for this agent");
      return null;
    }
    console.error("Error getting user agent subscription:", error);
    throw error;
  }
}

// Execute all operations
async function main() {
  try {
    // Initialize client
    const { program, wallet, walletPublicKey, connection, programAuthorityWallet } = await initializeClient();
    
    console.log("Connected to Solana Devnet");
    console.log(`Wallet: ${walletPublicKey.toBase58()}`);
    
    // Execute operations based on command line arguments
    const command = process.argv[2];
    
    if (command === 'init-fee-collector') {
      await initializeFeeCollector(program, programAuthorityWallet);
      return;
    }
    
    // For other commands, initialize fee collector PDA
    const [feeCollectorPDA] = PublicKey.findProgramAddressSync(
      [Buffer.from("fee_account")],
      program.programId
    );
    
    switch (command) {
      case 'mint':
        // Mint a new Agent NFT
        const metadataUrl = process.argv[3] || "https://example.com/agent/metadata.json";
        await mintAgentNFT(program, wallet,programAuthorityWallet, metadataUrl);
        break;
        
      case 'purchase':
        // Purchase a subscription
        const agentNftMintAddress = process.argv[3];
        const subscriptionType = process.argv[4] || "oneDay";
        
        if (!agentNftMintAddress) {
          console.error("Please provide the agent NFT mint address");
          process.exit(1);
        }
        
        const agentNftMint = new PublicKey(agentNftMintAddress);
        await purchaseSubscription(program, wallet, agentNftMint, subscriptionType, feeCollectorPDA);
        break;
        
      case 'withdraw-fees':
        // Withdraw fees
        const withdrawDestinationStr = process.argv[3] || wallet.publicKey.toBase58();
        const withdrawDestination = new PublicKey(withdrawDestinationStr);
        
        console.log(`Withdrawing fees to: ${withdrawDestination.toBase58()}`);
        await withdrawFees(program, programAuthorityWallet, withdrawDestination);
        break;
        
      case 'list-agents':
        // List all Agent NFTs
        await getAllAgentNFTs(program);
        break;
        
      case 'my-subscriptions':
        const userWalletStr = process.argv[3] || "";
        let userWallet = walletPublicKey;
        if(userWalletStr != ""){
          userWallet = new PublicKey(userWalletStr);
        }
        // List all subscriptions for the current user
        await getUserSubscriptions(program, userWallet);
        break;
        
      case 'get-subscription':
        // Get subscription for a specific agent
        const agentMintForSub = process.argv[3];
        
        if (!agentMintForSub) {
          console.error("Please provide the agent NFT mint address");
          process.exit(1);
        }
        const userWalletAddressStr = process.argv[4] || "";
        let userWalletAddress = walletPublicKey;
        if(userWalletAddressStr != ""){
          userWalletAddress = new PublicKey(userWalletAddressStr);
        }
        const agentMint = new PublicKey(agentMintForSub);
        await getUserAgentSubscription(program,userWalletAddress, agentMint);
        break;
        
      default:
        console.log(`
Available commands:
  node index.js init-fee-collector                        - Initialize fee collector PDA
  node index.js mint [metadata_url]                       - Mint a new Agent NFT
  node index.js purchase <agent_mint> [subscription_type] - Purchase a subscription
  node index.js withdraw-fees [destination]               - Withdraw fees to address (default: your wallet)
  node index.js list-agents                               - List all Agent NFTs
  node index.js my-subscriptions <your_wallet_address>    - List all your subscriptions
  node index.js get-subscription <agent_mint> <your_wallet_address> - Get subscription for specific agent
        `);
    }
    
  } catch (error) {
    console.error("Error executing operations:", error);
  }
}

main();
