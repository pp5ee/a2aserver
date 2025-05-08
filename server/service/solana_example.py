#!/usr/bin/env python
"""
Example usage of the SolanaService class.
This file demonstrates how to use the SolanaService to interact with Solana blockchain.
"""

import os
import logging
from solders.pubkey import Pubkey
from solana.rpc.commitment import Finalized

# Import our SolanaService
from solana_client import SolanaService, NetworkType

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Example 1: Initialize the service with devnet (default)
    solana_devnet = SolanaService()
    logger.info(f"Connected to {solana_devnet.network_type.value} at {solana_devnet.rpc_url}")
    
    # Example 2: Initialize the service with mainnet
    solana_mainnet = SolanaService(network_type=NetworkType.DEVNET)
    logger.info(f"Connected to {solana_mainnet.network_type.value} at {solana_mainnet.rpc_url}")
    
    # Example 3: Initialize with custom RPC URL and specific commitment
    custom_url = "https://my-custom-rpc-provider.com"
    solana_custom = SolanaService(
        network_type=NetworkType.DEVNET,
        custom_url=custom_url,
        commitment=Finalized
    )
    logger.info(f"Connected to custom RPC at {solana_custom.rpc_url}")
    
    # Example 4: Get account information
    try:
        # Example public key (Solana Program Library token program)
        token_program_id = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
        account_info = solana_devnet.get_account_info(token_program_id)
        #logger.info(f"Token Program Account Info: {account_info}")
    except Exception as e:
        
        logger.error(f"Error getting account info: {e}")
    
    # Example 5: Get program accounts
    try:
        # Set your program ID here
        program_id = os.getenv("PROGRAM_ID", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
        
        logger.info(f"Fetching all agent NFTs for program: {program_id}")
        agent_nfts = solana_devnet.get_agent_nfts(program_id)
        logger.info(f"Found {len(agent_nfts)} agent NFTs")
        
        # If we have agent NFTs, get details for the first one's owner
        if agent_nfts:
            owner = agent_nfts[0]["owner"]
            logger.info(f"Getting subscriptions for user: {owner}")
            
            subscriptions = solana_devnet.get_user_subscriptions(owner, program_id)
            logger.info(f"Found {len(subscriptions)} subscriptions for user")
            
            # If this user has a subscription, get specific agent subscription
            if subscriptions and "agent_nft_mint" in subscriptions[0]:
                agent_nft_mint = subscriptions[0]["agent_nft_mint"]
                logger.info(f"Getting specific subscription for agent: {agent_nft_mint}")
                
                subscription = solana_devnet.get_user_agent_subscription(
                    owner, agent_nft_mint, program_id
                )
                
                if subscription:
                    logger.info(f"Found subscription: {subscription}")
                else:
                    logger.info(f"No subscription found for this agent")
    except Exception as e:
        logger.error(f"Error in program operations: {e}")

if __name__ == "__main__":
    main() 