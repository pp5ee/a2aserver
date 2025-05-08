#!/usr/bin/env python
"""
Helper functions for working with Solana Program Derived Addresses (PDAs).
This provides similar functionality to the PDA-related code in the NodeJS implementation.
"""

from typing import List, Tuple, Union
import base58
from solders.pubkey import Pubkey

def find_program_address(seeds: List[bytes], program_id: Pubkey) -> Tuple[Pubkey, int]:
    """
    Find a valid program address and bump seed using the seeds and program id.
    
    This is the Python equivalent of Solana's findProgramAddress function.
    
    Args:
        seeds: List of seed bytes
        program_id: The program id
        
    Returns:
        Tuple of (program address, bump seed)
    """
    MAX_SEED_LENGTH = 32
    bump_seed = 255
    buffer = bytearray()
    
    for seed in seeds:
        if len(seed) > MAX_SEED_LENGTH:
            raise ValueError(f"Max seed length exceeded: {len(seed)}")
        buffer.extend(seed)
    
    buffer.extend(bytes(program_id))
    buffer.append(bump_seed)
    
    while bump_seed > 0:
        try:
            address = Pubkey.create_with_seed(
                Pubkey.from_bytes(bytes(buffer[:-1])),
                str(bump_seed),
                program_id
            )
            return address, bump_seed
        except Exception:
            bump_seed -= 1
            buffer[-1] = bump_seed
    
    raise ValueError("Unable to find a valid program address")

def get_agent_nft_pda(nft_mint: Union[str, Pubkey], program_id: Union[str, Pubkey]) -> Pubkey:
    """
    Get the PDA for an Agent NFT.
    
    Args:
        nft_mint: The NFT mint address
        program_id: The program ID
        
    Returns:
        The Agent NFT PDA
    """
    if isinstance(nft_mint, str):
        nft_mint = Pubkey.from_string(nft_mint)
    
    if isinstance(program_id, str):
        program_id = Pubkey.from_string(program_id)
    
    # Equivalent to [Buffer.from("agent-nft"), nftMint.toBuffer()]
    seeds = [
        b"agent-nft",
        bytes(nft_mint)
    ]
    
    pda, _ = find_program_address(seeds, program_id)
    return pda

def get_subscription_pda(
    user_pubkey: Union[str, Pubkey], 
    agent_nft_mint: Union[str, Pubkey], 
    program_id: Union[str, Pubkey]
) -> Pubkey:
    """
    Get the PDA for a user subscription to an Agent NFT.
    
    Args:
        user_pubkey: The user's public key
        agent_nft_mint: The Agent NFT mint address
        program_id: The program ID
        
    Returns:
        The Subscription PDA
    """
    if isinstance(user_pubkey, str):
        user_pubkey = Pubkey.from_string(user_pubkey)
    
    if isinstance(agent_nft_mint, str):
        agent_nft_mint = Pubkey.from_string(agent_nft_mint)
    
    if isinstance(program_id, str):
        program_id = Pubkey.from_string(program_id)
    
    # Equivalent to [Buffer.from("subscription"), userPublicKey.toBuffer(), agentNftMint.toBuffer()]
    seeds = [
        b"subscription",
        bytes(user_pubkey),
        bytes(agent_nft_mint)
    ]
    
    pda, _ = find_program_address(seeds, program_id)
    return pda

def get_associated_token_address(
    mint: Union[str, Pubkey],
    owner: Union[str, Pubkey],
    token_program_id: Union[str, Pubkey] = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    associated_token_program_id: Union[str, Pubkey] = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
) -> Pubkey:
    """
    Get the associated token address for an SPL token.
    
    Args:
        mint: The mint address
        owner: The token account owner
        token_program_id: The token program ID
        associated_token_program_id: The associated token program ID
        
    Returns:
        The associated token address
    """
    if isinstance(mint, str):
        mint = Pubkey.from_string(mint)
    
    if isinstance(owner, str):
        owner = Pubkey.from_string(owner)
    
    if isinstance(token_program_id, str):
        token_program_id = Pubkey.from_string(token_program_id)
    
    if isinstance(associated_token_program_id, str):
        associated_token_program_id = Pubkey.from_string(associated_token_program_id)
    
    # Equivalent to [owner.toBuffer(), TOKEN_PROGRAM_ID.toBuffer(), mint.toBuffer()]
    seeds = [
        bytes(owner),
        bytes(token_program_id),
        bytes(mint)
    ]
    
    pda, _ = find_program_address(seeds, associated_token_program_id)
    return pda 