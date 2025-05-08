
# create  .env file
set up your environment variables in the .env file with your private key and program ID. The private key should be an array format as exported by Solana CLI or wallets.
``` bash
WALLET_PRIVATE_KEY=your_private_key_here
PROGRAM_ID=smart_contract_program_id_here
```
# mv idl file to current dir
```bash
#after anchor build
#default idl file is project_root_dir/target/idl/project_name.json
```

# How to use
``` bash
# Mint a new Agent NFT
node index.js mint "https://example.com/my-agent-metadata.json"

# Purchase a  subscription
node index.js purchase YOUR_AGENT_NFT_MINT_ADDRESS oneDay/sevenDays/thirtyDays/yearly

# List all Agent NFTs
node index.js list-agents

# List all your subscriptions
node index.js my-subscriptions

# Get subscription for a specific agent
node index.js get-subscription YOUR_AGENT_NFT_MINT_ADDRESS
```
