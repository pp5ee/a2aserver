# Solana Service for A2A Server

This service provides a Python wrapper for interacting with the Solana blockchain, supporting both mainnet and devnet configurations.

## Features

- Connect to Solana mainnet, devnet, testnet, or localnet
- Support for custom RPC endpoints
- Retrieve account information and balances
- Get token accounts by owner
- Get program accounts with filtering
- Get transaction details
- Specialized methods for working with Agent NFTs and subscriptions

## Installation

The necessary dependencies are already included in the project's `pyproject.toml`:

```
solana>=0.32.0
solders>=0.22.0
PyNaCl>=1.5.0
```

## Basic Usage

### Initializing the Service

```python
from service.solana_client import SolanaService, NetworkType

# Connect to devnet (default)
solana_devnet = SolanaService()

# Connect to mainnet
solana_mainnet = SolanaService(network_type=NetworkType.MAINNET)

# Connect with custom URL
solana_custom = SolanaService(
    network_type=NetworkType.MAINNET,
    custom_url="https://my-custom-rpc-provider.com"
)
```

### Getting Account Information

```python
# Get account info
account_info = solana_service.get_account_info("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

# Get account balance (in lamports)
balance = solana_service.get_balance("YourWalletAddressHere")
```

### Working with Program Accounts

```python
# Get all accounts owned by a program
program_id = "YourProgramIdHere"
accounts = solana_service.get_program_accounts(program_id)

# Get accounts with filters
filters = [{
    "memcmp": {
        "offset": 8,  # Skip discriminator
        "bytes": "SomePublicKeyHere"
    }
}]
filtered_accounts = solana_service.get_program_accounts(program_id, filters)
```

### Agent NFT and Subscription Methods

```python
# Get all agent NFTs
agent_nfts = solana_service.get_agent_nfts(program_id)

# Get user subscriptions
user_pubkey = "UserPublicKeyHere"
subscriptions = solana_service.get_user_subscriptions(user_pubkey, program_id)

# Get specific subscription
agent_nft_mint = "AgentNftMintHere"
subscription = solana_service.get_user_agent_subscription(
    user_pubkey, 
    agent_nft_mint,
    program_id
)
```

## Environment Configuration

It's recommended to store sensitive configuration in environment variables:

```python
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

program_id = os.getenv("SOLANA_PROGRAM_ID")
```

## Examples

Check the `solana_example.py` file for complete usage examples.

## Notes on Production Use

- For production environments, consider using a paid RPC provider rather than the public endpoints
- Implement appropriate error handling and retries for RPC calls
- Consider implementing caching for frequently accessed data

## Customization

The current implementation needs to be customized based on your specific program's account structures:

1. Update the filtering logic in `get_agent_nfts`, `get_user_subscriptions`, and `get_user_agent_subscription`
2. Implement proper data deserialization based on your Anchor program's account layouts
3. Add any additional methods specific to your application's needs 