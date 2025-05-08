const { SystemProgram,Connection, Keypair, PublicKey, LAMPORTS_PER_SOL, sendAndConfirmTransaction, SYSVAR_CLOCK_PUBKEY } = require('@solana/web3.js');
const { Program, AnchorProvider, Wallet, BN } = require('@coral-xyz/anchor');

const { TOKEN_PROGRAM_ID } = require('@solana/spl-token');
const fs = require('fs');
require('dotenv').config();

// Load IDL from file
// const idlFile = './agent_nft_market.json';
// const idl = JSON.parse(fs.readFileSync(idlFile, 'utf8'));
const idl = require("./agent_nft_market.json");
console.log(idl.address);
// Constants
const PROGRAM_ID = new PublicKey(process.env.PROGRAM_ID);
const DEVNET_URL = 'https://api.devnet.solana.com';
const ASSOCIATED_TOKEN_PROGRAM_ID = new PublicKey('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL');

// Initialize connection and wallet
async function initializeClient() {
  const connection = new Connection(DEVNET_URL, 'confirmed');
  
  // Load wallet from private key
  const walletKeypair = Keypair.fromSecretKey(
    Buffer.from(JSON.parse(process.env.WALLET_PRIVATE_KEY))
  );
  
  const wallet = new Wallet(walletKeypair);
  const provider = new AnchorProvider(
    connection, 
    wallet,
    { commitment: 'confirmed' }
  );
  
  const program = new Program(idl, provider);
  
  return { 
    connection, 
    wallet: wallet, 
    walletPublicKey: walletKeypair.publicKey, 
    provider, 
    program 
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

// Mint a new Agent NFT
async function mintAgentNFT(program, owner, metadataUrl) {
  console.log(`Minting a new Agent NFT for ${owner.toBase58()}`);
  console.log(`Metadata URL: ${metadataUrl}`);
  
  // Generate a new keypair for the NFT mint
  const nftMintKeypair = Keypair.generate();
  const nftMint = nftMintKeypair.publicKey;
  
  console.log(`NFT Mint: ${nftMint.toBase58()}`);
  console.log(`program.programId: ${program.programId}`);
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
        owner: owner,
        programAuthority: owner,
        mint: nftMint,
        agentNft: agentNftPDA,
        tokenAccount: await getAssociatedTokenAddress(
          nftMint,
          owner
        ),
        tokenProgram: TOKEN_PROGRAM_ID,
        associatedTokenProgram: ASSOCIATED_TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: new PublicKey('SysvarRent111111111111111111111111111111111'),
        clock: new PublicKey('SysvarC1ock11111111111111111111111111111111'),
      })
      .signers([nftMintKeypair])
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
async function purchaseSubscription(program, user, agentNftMint, subscriptionType) {
  console.log(`Purchasing a ${subscriptionType} subscription for ${user.publicKey.toBase58()}`);
  
   // Find the AgentNft PDA
  const [agentNftPDA] = PublicKey.findProgramAddressSync(
    [Buffer.from("agent-nft"), agentNftMint.toBuffer()],
    program.programId
  );
  console.log(`agentNftPDA: ${agentNftPDA.toBase58()}`);

  const agentNftAccount = await program.account.agentNft.fetch(agentNftPDA);
  const paymentDestination = agentNftAccount.owner;
  // Log the Agent NFT Mint and payment destination
  console.log(`Agent NFT Mint: ${agentNftMint.toBase58()}`);
  console.log(`paymentDestination: ${paymentDestination.toBase58()}`);

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
  
  // Convert subscription type to the contract's enum format
  // Options: { oneDay: {} }, { sevenDays: {} }, { thirtyDays: {} }, { yearly: {} }
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
      throw new Error(`Invalid subscription type: ${subscriptionType}`);
  }
  
  try {
    // Purchase the subscription
    const tx = await program.methods
      .purchaseSubscription(subscriptionTypeArg)
      .accounts({
        user: user.publicKey,
        agentNft: agentNftPDA,
        agentNftMint: agentNftMint,
        subscription: subscriptionPDA,
        paymentDestination: paymentDestination,
        systemProgram: SystemProgram.programId,
        clock: SYSVAR_CLOCK_PUBKEY,
      })
      .signers([user.payer])
      .rpc();
    
    console.log(`Subscription purchased successfully! Transaction signature: ${tx}`);
    
    // Fetch the subscription account to verify
    const subscriptionAccount = await program.account.subscription.fetch(subscriptionPDA);
    
    console.log(`Subscription Account:
      - User: ${subscriptionAccount.user.toBase58()}
      - Agent NFT Mint: ${subscriptionAccount.agentNftMint.toBase58()}
      - Expires At: ${new Date(subscriptionAccount.expiresAt.toNumber() * 1000).toLocaleString()}
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
        
        // Log subscription details
        console.log(`Subscription #${index + 1}:`);
        console.log(`  - Address: ${subscriptionAccount.publicKey.toBase58()}`);
        console.log(`  - Agent NFT Mint: ${subscription.agentNftMint.toBase58()}`);
        console.log(`  - Agent NFT Metadata URL: ${agentNft.metadataUrl}`);
        console.log(`  - Expires At: ${new Date(subscription.expiresAt.toNumber() * 1000).toLocaleString()}`);
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
    
    console.log(`Subscription Details: ${subscriptionInfo}`);
    console.log(`  - User: ${userPublicKey.toBase58()}`);
    console.log(`  - Agent NFT Mint: ${subscriptionInfo.agentNftMint.toBase58()}`);
    console.log(`  - Agent NFT Metadata URL: ${subscriptionInfo.metadataUrl}`);
    console.log(`  - Expires At: ${new Date(subscriptionInfo.expiresAt.toNumber() * 1000).toLocaleString()}`);
    console.log(`  - Status: ${isActive ? 'Active' : 'Expired'}`);
    
    return {
      ...subscriptionInfo,
      isActive
    };
  } catch (error) {
    if (error.simulationResponse != null && error.simulationResponse.logs.join(",").includes("AccountNotInitialized")) {
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
    const { program,wallet, walletPublicKey } = await initializeClient();
    
    console.log("Connected to Solana Devnet");
    console.log(`Wallet: ${walletPublicKey.toBase58()}`);
    
    // Execute operations based on command line arguments
    const command = process.argv[2];
    
    switch (command) {
      case 'mint':
        // Mint a new Agent NFT
        const metadataUrl = process.argv[3] || "https://example.com/agent/metadata.json";
        await mintAgentNFT(program, walletPublicKey, metadataUrl);
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
        await purchaseSubscription(program, wallet, agentNftMint, subscriptionType);
        break;
        
      case 'list-agents':
        // List all Agent NFTs
        await getAllAgentNFTs(program);
        break;
        
      case 'my-subscriptions':
        // List all subscriptions for the current user
        await getUserSubscriptions(program, walletPublicKey);
        break;
        
      case 'get-subscription':
        // Get subscription for a specific agent
        const agentMintForSub = process.argv[3];
        
        if (!agentMintForSub) {
          console.error("Please provide the agent NFT mint address");
          process.exit(1);
        }
        
        const agentMint = new PublicKey(agentMintForSub);
        await getUserAgentSubscription(program, walletPublicKey, agentMint);
        break;
        
      default:
        console.log(`
Available commands:
  node index.js mint [metadata_url]                  - Mint a new Agent NFT
  node index.js purchase <agent_mint> [subscription_type] - Purchase a subscription
  node index.js list-agents                          - List all Agent NFTs
  node index.js my-subscriptions                     - List all your subscriptions
  node index.js get-subscription <agent_mint>        - Get subscription for specific agent
        `);
    }
    
  } catch (error) {
    console.error("Error executing operations:", error);
  }
}

main();
