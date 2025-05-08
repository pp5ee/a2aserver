#!/usr/bin/env python
import os
import json
import logging
from typing import Optional, Dict, List, Union, Any
from enum import Enum
import base64
import time

# Import Solana modules
from solana.rpc.api import Client as SolanaClient
from solana.exceptions import SolanaRpcException
from solders.pubkey import Pubkey
from solders.signature import Signature
from solana.rpc.types import TokenAccountOpts
from solana.rpc.commitment import Commitment, Confirmed, Finalized, Processed

# Import PDA helper functions
from solana_pda_helper import (
    get_agent_nft_pda, 
    get_subscription_pda, 
    get_associated_token_address
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NetworkType(Enum):
    MAINNET = "mainnet-beta"
    DEVNET = "devnet"
    TESTNET = "testnet"
    LOCALNET = "localnet"

class SolanaService:
    """
    A service class to interact with Solana blockchain.
    Supports mainnet and devnet configurations.
    """
    
    # RPC endpoint URLs
    RPC_URLS = {
        NetworkType.MAINNET: "https://api.mainnet-beta.solana.com",
        NetworkType.DEVNET: "https://api.devnet.solana.com",
        NetworkType.TESTNET: "https://api.testnet.solana.com",
        NetworkType.LOCALNET: "http://localhost:8899",
    }
    
    def __init__(self, network_type: NetworkType = NetworkType.DEVNET, 
                 custom_url: Optional[str] = None, 
                 commitment: Commitment = Confirmed):
        """
        Initialize the Solana service.
        
        Args:
            network_type: The network to connect to (mainnet, devnet, testnet, localnet)
            custom_url: Optional custom RPC URL to use instead of the default
            commitment: The commitment level for transactions (Confirmed, Finalized, Processed)
        """
        self.network_type = network_type
        self.rpc_url = custom_url or self.RPC_URLS[network_type]
        self.commitment = commitment
        logger.info(f"Initializing Solana client with {network_type.value} at {self.rpc_url}")
        self.client = SolanaClient(self.rpc_url)
        
    def get_account_info(self, pubkey: Union[str, Pubkey]) -> Dict:
        """Get information about an account."""
        try:
            if isinstance(pubkey, str):
                pubkey = Pubkey.from_string(pubkey)
                
            response = self.client.get_account_info(pubkey, commitment=self.commitment)
            return response.value
        except SolanaRpcException as e:
            logger.error(f"Error getting account info for {pubkey}: {e}")
            raise

    def get_balance(self, pubkey: Union[str, Pubkey]) -> int:
        """Get the SOL balance of an account."""
        try:
            if isinstance(pubkey, str):
                pubkey = Pubkey.from_string(pubkey)
                
            response = self.client.get_balance(pubkey, commitment=self.commitment)
            return response.value
        except SolanaRpcException as e:
            logger.error(f"Error getting balance for {pubkey}: {e}")
            raise

    def get_token_accounts_by_owner(self, owner: Union[str, Pubkey], 
                                    program_id: Optional[Union[str, Pubkey]] = None, 
                                    mint: Optional[Union[str, Pubkey]] = None) -> List[Dict]:
        """Get token accounts for a specific owner."""
        try:
            if isinstance(owner, str):
                owner = Pubkey.from_string(owner)
            
            opts = TokenAccountOpts()
            
            if program_id:
                if isinstance(program_id, str):
                    program_id = Pubkey.from_string(program_id)
                opts.program_id = program_id
                
            if mint:
                if isinstance(mint, str):
                    mint = Pubkey.from_string(mint)
                opts.mint = mint
                
            response = self.client.get_token_accounts_by_owner(
                owner, 
                opts,
                commitment=self.commitment
            )
            return response.value
        except SolanaRpcException as e:
            logger.error(f"Error getting token accounts for {owner}: {e}")
            raise

    def get_program_accounts(self, program_id: Union[str, Pubkey], 
                           filters: Optional[List[Dict]] = None) -> List[Dict]:
        """Get all accounts owned by a program."""
        try:
            if isinstance(program_id, str):
                program_id = Pubkey.from_string(program_id)
                
            response = self.client.get_program_accounts(
                program_id,
                filters=filters,
                commitment=self.commitment
            )
            return response.value
        except SolanaRpcException as e:
            logger.error(f"Error getting program accounts for {program_id}: {e}")
            raise

    def get_transaction(self, signature: Union[str, Signature]) -> Dict:
        """Get transaction details by signature."""
        try:
            if isinstance(signature, str):
                signature = Signature.from_string(signature)
                
            response = self.client.get_transaction(
                signature, 
                commitment=self.commitment
            )
            return response.value
        except SolanaRpcException as e:
            logger.error(f"Error getting transaction {signature}: {e}")
            raise

    def get_agent_nfts(self, program_id: Union[str, Pubkey]) -> List[Dict]:
        """
        Get all Agent NFTs from the program.
        Similar to getAllAgentNFTs in the nodejs implementation.
        """
        try:
            if isinstance(program_id, str):
                program_id = Pubkey.from_string(program_id)
                
            # Get all program accounts with a filter to match the AgentNft account discriminator
            # This would need to be adapted with the actual discriminator
            # In Anchor, the discriminator is the first 8 bytes of the SHA256 hash of the account name
            accounts = self.get_program_accounts(program_id)
            
            # Process and return the accounts
            agent_nfts = []
            for account in accounts:
                try:
                    # You would need to deserialize the account data based on your Anchor IDL
                    # This is a placeholder implementation
                    agent_nfts.append({
                        "publicKey": str(account.pubkey),
                        "owner": str(account.account.owner),
                        "mint": "placeholder_mint",  # You would extract this from the deserialized data
                        "metadataUrl": "placeholder_url"  # You would extract this from the deserialized data
                    })
                except Exception as e:
                    logger.warning(f"Error processing account {account.pubkey}: {e}")
                    continue
                
            return agent_nfts
        except SolanaRpcException as e:
            logger.error(f"Error getting Agent NFTs for program {program_id}: {e}")
            raise

    def get_user_subscriptions(self, 
                             user_pubkey: Union[str, Pubkey], 
                             program_id: Union[str, Pubkey]) -> List[Dict]:
        """
        Get all subscriptions for a specific user.
        Similar to getUserSubscriptions in the nodejs implementation.
        """
        try:
            if isinstance(user_pubkey, str):
                user_pubkey = Pubkey.from_string(user_pubkey)
                
            if isinstance(program_id, str):
                program_id = Pubkey.from_string(program_id)
            
            # Get all program accounts with a filter for the user's public key
            # Assuming the user's pubkey is stored at offset 8 (after discriminator)
            filters = [
                {
                    "memcmp": {
                        "offset": 8,  # Skip discriminator
                        "bytes": str(user_pubkey)
                    }
                }
            ]
            
            accounts = self.get_program_accounts(program_id, filters)
            
            # Process subscriptions and add metadata
            subscriptions = []
            for account in accounts:
                try:
                    # You would need to deserialize the account data based on your Anchor IDL
                    # This is a placeholder implementation
                    agent_nft_mint = "placeholder_mint"  # Extract from deserialized data
                    expires_at = int(time.time()) + 86400  # Example: 1 day from now
                    
                    # Get the Agent NFT PDA to fetch metadata
                    agent_nft_pda = get_agent_nft_pda(agent_nft_mint, program_id)
                    agent_nft_account = self.get_account_info(agent_nft_pda)
                    
                    # In a real implementation, you would deserialize the agent_nft_account data
                    metadata_url = "placeholder_url"  # Extract from agent_nft_account
                    
                    # Check if subscription is active
                    is_active = expires_at > int(time.time())
                    
                    subscriptions.append({
                        "address": str(account.pubkey),
                        "agentNftMint": agent_nft_mint,
                        "agentNftMetadataUrl": metadata_url,
                        "expiresAt": expires_at,
                        "isActive": is_active
                    })
                except Exception as e:
                    logger.warning(f"Error processing subscription {account.pubkey}: {e}")
                    continue
                
            return subscriptions
        except SolanaRpcException as e:
            logger.error(f"Error getting subscriptions for user {user_pubkey}: {e}")
            raise

    def get_user_agent_subscription(self, 
                                  user_pubkey: Union[str, Pubkey], 
                                  agent_nft_mint: Union[str, Pubkey],
                                  program_id: Union[str, Pubkey]) -> Optional[Dict]:
        """
        Get a specific subscription for a user and agent NFT.
        Similar to getUserAgentSubscription in the nodejs implementation.
        """
        try:
            if isinstance(user_pubkey, str):
                user_pubkey = Pubkey.from_string(user_pubkey)
                
            if isinstance(agent_nft_mint, str):
                agent_nft_mint = Pubkey.from_string(agent_nft_mint)
                
            if isinstance(program_id, str):
                program_id = Pubkey.from_string(program_id)
            
            # Find the AgentNft PDA
            agent_nft_pda = get_agent_nft_pda(agent_nft_mint, program_id)
            
            # Find the Subscription PDA
            subscription_pda = get_subscription_pda(
                user_pubkey, 
                agent_nft_mint, 
                program_id
            )
            
            # Try to get the subscription account
            try:
                subscription_account = self.get_account_info(subscription_pda)
                
                if not subscription_account:
                    return None
                
                # Also get the Agent NFT account to get metadata
                agent_nft_account = self.get_account_info(agent_nft_pda)
                
                # In a real implementation, you would deserialize both accounts' data
                # This is a placeholder implementation
                expires_at = int(time.time()) + 86400  # Example: 1 day from now
                metadata_url = "placeholder_url"  # Extract from agent_nft_account
                
                # Check if subscription is active
                is_active = expires_at > int(time.time())
                
                return {
                    "address": str(subscription_pda),
                    "user": str(user_pubkey),
                    "agentNftMint": str(agent_nft_mint),
                    "metadataUrl": metadata_url,
                    "expiresAt": expires_at,
                    "isActive": is_active
                }
            except Exception:
                # If the account doesn't exist or an error occurred
                return None
                
        except SolanaRpcException as e:
            logger.error(f"Error getting subscription for user {user_pubkey} and agent {agent_nft_mint}: {e}")
            raise 