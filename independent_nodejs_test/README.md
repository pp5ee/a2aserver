
# create  .env file
set up your environment variables in the .env file with your private key and program ID. The private key should be an array format as exported by Solana CLI or wallets.
``` bash
WALLET_PRIVATE_KEY=your_private_key_here
PROGRAM_AUTHORITY_PRIVATE_KEY=program_authority_private_key_here
PROGRAM_ID=smart_contract_program_id_here
```
# mv idl file to current dir
```bash
#after anchor build
#default idl file is project_root_dir/target/idl/project_name.json
```

# How to use
``` bash
# Initialize fee collector PDA,call once after contract deploy
node index.js init-fee-collector

# Mint a new Agent NFT
node index.js mint [metadata_url]

# Purchase a subscription
node index.js purchase <agent_mint> [subscription_type]
# subscription_type can be: oneDay, sevenDays, thirtyDays, yearly

# Withdraw accumulated fees
node index.js withdraw-fees [destination]

# List all Agent NFTs
node index.js list-agents

# List all subscriptions for a wallet
node index.js my-subscriptions [wallet_address]

# Get specific subscription info
node index.js get-subscription <agent_mint> [wallet_address]
```
