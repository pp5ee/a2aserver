# -*- coding: utf-8 -*-
import logging
import time
import base64
import datetime
from typing import Optional, Tuple, List, Dict, Any

# 配置日志 - 修改日志级别为WARNING，减少输出
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Solana网络和程序配置 - 集中配置项
SOLANA_CONFIG = {
    "NETWORK_URL": "https://api.devnet.solana.com",  # Solana网络URL
    "PROGRAM_ID": "3Qqf9EXWLDhr9bzxdgUk6UQbDYuynAS5WKT5ygpYpQfQ",  # 程序ID
    "FEE_COLLECTOR_SEED": "fee_account",  # 费用收集器种子
    "AGENT_NFT_SEED": "agent-nft",  # Agent NFT种子
    "SUBSCRIPTION_SEED": "subscription",  # 订阅种子
    # 可以添加更多配置
}

# 导入Solana相关库
sdk_available = False
try:
    # 使用solders包提供的PublicKey替代solana.publickey
    from solders.pubkey import Pubkey as PublicKey
    from solders.signature import Signature
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError
    sdk_available = True
except ImportError as e:
    logger.warning(f"Solana SDK不可用，验证将失败。请安装依赖: pip install solana solders PyNaCl，错误: {e}")

class SolanaVerifier:
    """
    验证Solana钱包签名的实用工具类
    """
    def __init__(self):
        self.logger = logger
        self.sdk_available = sdk_available
        if not self.sdk_available:
            self.logger.error("Solana SDK未安装，所有签名验证将失败，系统安全风险高")
    
    def verify_signature(self, public_key: str, nonce: str, signature: str) -> bool:
        """
        验证签名是否有效
        
        Args:
            public_key: Solana钱包地址
            nonce: 签名到期的毫秒级时间戳
            signature: 签名后的字符串（Base64编码）
        
        Returns:
            bool: 签名是否有效
        """
        # 检查SDK是否可用，如果不可用，直接返回验证失败
        if not self.sdk_available:
            self.logger.error("验证失败: Solana SDK未安装，无法验证签名")
            return False
            
        # 检查是否所有参数都存在
        if not public_key or not nonce or not signature:
            self.logger.warning(f"验证失败: 缺少必要参数, public_key={public_key}, nonce={nonce}, signature={signature}")
            return False
        
        # 验证签名
        try:
            nonce_timestamp = int(nonce)
            current_time = int(time.time() * 1000)  # 当前毫秒时间戳
            
            # 检查签名是否过期
            if current_time > nonce_timestamp:
                self.logger.warning(f"验证失败: 签名已过期, current_time={current_time}, nonce_timestamp={nonce_timestamp}")
                return False
            
            # 使用SDK进行真正的签名验证
            is_valid, error_msg = self._verify_with_solana_sdk(public_key, nonce, signature)
            if not is_valid:
                self.logger.warning(f"验证失败: {error_msg}")
                return False
            
            self.logger.info(f"验证成功: public_key={public_key[:10]}...")
            return True
            
        except Exception as e:
            self.logger.warning(f"验证失败: 发生异常 {str(e)}")
            return False
    
    def _verify_with_solana_sdk(self, public_key: str, nonce: str, signature_base64: str) -> Tuple[bool, Optional[str]]:
        """
        使用Solana SDK验证签名
        
        Args:
            public_key: Solana钱包地址
            nonce: 时间戳
            signature_base64: Base64编码的签名
            
        Returns:
            Tuple[bool, Optional[str]]: (是否验证成功, 错误信息)
        """
        try:
            # 1. 获取签名消息
            # 直接使用nonce作为签名内容
            message_bytes = nonce.encode('utf-8')
            
            # 2. 解码Base64签名
            try:
                signature_bytes = base64.b64decode(signature_base64)
            except Exception as e:
                return False, f"Invalid signature format: {str(e)}"
            
            # 3. 创建Solana PublicKey对象
            try:
                # 使用新版solders的Pubkey
                pk = PublicKey.from_string(public_key)
                verify_key = VerifyKey(bytes(pk))
            except Exception as e:
                return False, f"Invalid public key: {str(e)}"
            
            # 4. 验证签名
            try:
                verify_key.verify(message_bytes, signature_bytes)
                return True, None
            except BadSignatureError:
                return False, "Signature verification failed"
            except Exception as e:
                return False, f"Verification process error: {str(e)}"
                
        except Exception as e:
            return False, f"Unexpected error during verification: {str(e)}"

# 创建一个全局实例方便使用（仅当SDK可用时才创建）
solana_verifier = SolanaVerifier() 

def print_response_structure(response, prefix=""):
    """
    打印响应对象的结构，用于调试
    
    Args:
        response: 响应对象
        prefix: 前缀，用于缩进
    """
    if response is None:
        logger.debug(f"{prefix}None")
        return
        
    if isinstance(response, (str, int, float, bool)):
        logger.debug(f"{prefix}{type(response).__name__}: {response}")
        return
        
    if isinstance(response, list):
        logger.debug(f"{prefix}List[{len(response)}]:")
        if len(response) > 0:
            print_response_structure(response[0], prefix + "  ")
        return
        
    if isinstance(response, dict):
        logger.debug(f"{prefix}Dict:")
        for key, value in response.items():
            logger.debug(f"{prefix}  {key}:")
            print_response_structure(value, prefix + "    ")
        return
        
    # 对象
    logger.debug(f"{prefix}{type(response).__name__}:")
    for attr in dir(response):
        if not attr.startswith("_") and not callable(getattr(response, attr)):
            try:
                value = getattr(response, attr)
                logger.debug(f"{prefix}  {attr}:")
                print_response_structure(value, prefix + "    ")
            except Exception as e:
                logger.debug(f"{prefix}  {attr}: <Error: {e}>")

async def get_user_subscriptions(wallet_address: str) -> List[Dict[str, Any]]:
    """
    从Solana区块链获取用户的NFT订阅状态，基于NodeJS实现
    
    Args:
        wallet_address: 用户的钱包地址
        
    Returns:
        List[Dict[str, Any]]: 用户有效的NFT订阅列表，每个订阅包含nft_mint_id、agent_url和expire_at
    """
    logger.info(f"获取用户 {wallet_address} 的NFT订阅状态")
    
    try:
        # 检查SDK是否可用
        if not sdk_available:
            logger.warning("Solana SDK不可用，无法获取用户订阅")
            return []
        
        # 导入必要的模块
        try:
            from solders.pubkey import Pubkey as PublicKey
            from solana.rpc.api import Client
            import base58
            import json
            import base64
            from solana.rpc.types import MemcmpOpts
            import os
        except ImportError as e:
            logger.error(f"导入模块失败: {e}")
            return []
        
        # 从集中配置获取程序ID
        try:
            PROGRAM_ID = PublicKey.from_string(SOLANA_CONFIG["PROGRAM_ID"])
            logger.info(f"使用配置的程序ID: {PROGRAM_ID}")
        except Exception as e:
            logger.error(f"使用配置的程序ID失败: {e}")
            return []
        
        # 连接到Solana网络
        try:
            # 使用配置的网络URL
            connection = Client(SOLANA_CONFIG["NETWORK_URL"])
            logger.debug(f"已连接到Solana节点: {SOLANA_CONFIG['NETWORK_URL']}")
        except Exception as e:
            logger.error(f"连接Solana节点失败: {e}")
            return []
        
        # 将钱包地址转换为PublicKey
        try:
            user_pubkey = PublicKey.from_string(wallet_address)
        except Exception as e:
            logger.error(f"转换钱包地址失败: {e}")
            return []
        
        # 使用与NodeJS测试相同的方法获取用户的所有订阅
        try:
            # 获取所有匹配Subscription类型且用户是指定钱包的账户
            # 1. 使用order判别器过滤
            subscription_discriminator = bytes.fromhex("40071a8766846221")
            
            # 2. 创建过滤器 - 按用户公钥过滤
            filters = [
                # 按Subscription类型过滤
                MemcmpOpts(
                    offset=0,  # 账户判别器位置
                    bytes=base58.b58encode(subscription_discriminator).decode('utf-8')
                ),
                # 按用户公钥过滤
                MemcmpOpts(
                    offset=8,  # 用户公钥在账户中的位置（跳过判别器8字节）
                    bytes=str(user_pubkey)
                )
            ]
            
            # 3. 获取用户的订阅账户
            logger.debug(f"查询用户 {wallet_address} 的订阅账户...")
            response = connection.get_program_accounts(
                PROGRAM_ID,
                encoding="base64",
                filters=filters
            )
            
            # 检查响应
            if not response.value:
                logger.info(f"用户 {wallet_address} 没有订阅账户")
                return []
            
            logger.info(f"找到 {len(response.value)} 个订阅账户")
            
            # 处理每个订阅账户
            subscriptions = []
            now = datetime.datetime.now()
            
            # 使用Promise.all模式并行处理所有订阅
            for account in response.value:
                try:
                    # 获取账户数据并解码
                    account_data = account.account.data
                    account_pubkey = account.pubkey
                    
                    # 跳过判别器(8字节)
                    # 订阅结构: discriminator(8) + user(32) + agent_nft_mint(32) + expires_at(8)
                    
                    # 提取用户公钥和NFT mint ID
                    user_data = account_data[8:40]  # 用户公钥 (32字节)
                    nft_mint_data = account_data[40:72]  # NFT mint ID (32字节)
                    
                    user_address = str(PublicKey.from_bytes(user_data))
                    nft_mint_id = str(PublicKey.from_bytes(nft_mint_data))
                    
                    # 提取过期时间 (8字节，小端序整数)
                    expires_at_seconds = int.from_bytes(account_data[72:80], byteorder='little')
                    expire_at = datetime.datetime.fromtimestamp(expires_at_seconds)
                    
                    # 检查用户地址是否匹配（额外验证）
                    if user_address != wallet_address:
                        logger.warning(f"账户数据中的用户地址不匹配：{user_address} != {wallet_address}")
                        continue
                    
                    logger.debug(f"找到订阅: NFT={nft_mint_id}, 过期时间={expire_at}")
                    
                    # 使用NodeJS实现的方式查找AgentNft PDA
                    # [Buffer.from("agent-nft"), subscription.agentNftMint.toBuffer()]
                    nft_mint_pubkey = PublicKey.from_string(nft_mint_id)
                    agent_nft_seed = SOLANA_CONFIG["AGENT_NFT_SEED"].encode('utf-8')
                    
                    # 查找PDA (使用类似PublicKey.findProgramAddressSync的实现)
                    pda_found = False
                    agent_nft_pda = None
                    
                    for bump in range(256):
                        try:
                            # 构建种子
                            seeds = [
                                agent_nft_seed,
                                bytes(nft_mint_pubkey)
                            ]
                            
                            # 计算PDA
                            address = PublicKey.find_program_address(
                                seeds=seeds,
                                program_id=PROGRAM_ID
                            )
                            
                            agent_nft_pda = address[0]  # PDA地址
                            pda_found = True
                            logger.debug(f"找到AgentNft PDA: {agent_nft_pda}")
                            break
                        except Exception as pda_error:
                            if bump == 255:
                                logger.error(f"无法找到AgentNft PDA: {pda_error}")
                    
                    # 如果找不到PDA，跳过该订阅
                    if not pda_found or not agent_nft_pda:
                        logger.error("找不到AgentNft PDA，跳过该订阅")
                        continue
                    
                    # 获取AgentNft账户数据
                    agent_nft_account = connection.get_account_info(agent_nft_pda)
                    
                    # 如果账户不存在，跳过该订阅
                    if not agent_nft_account.value:
                        logger.warning(f"AgentNft账户不存在: {agent_nft_pda}")
                        continue
                    
                    # 解析AgentNft账户数据，提取metadataUrl
                    agent_data = agent_nft_account.value.data
                    agent_url = "unknown"  # 默认值
                    
                    # AgentNft结构: discriminator(8) + owner(32) + mint(32) + metadataUrl(string)
                    # string结构: length(4) + content(variable)
                    
                    # 提取URL字符串长度
                    if len(agent_data) >= 76:  # 至少有8+32+32+4字节
                        str_len = int.from_bytes(agent_data[72:76], byteorder='little')
                        
                        if 0 < str_len < 1000 and 76 + str_len <= len(agent_data):
                            url_bytes = agent_data[76:76+str_len]
                            try:
                                agent_url = url_bytes.decode('utf-8')
                                
                                # 处理URL，确保格式正确
                                agent_url = validate_and_process_metadata_url(agent_url)
                                                                
                                logger.debug(f"提取到的代理URL: {agent_url}")
                            except Exception as e:
                                logger.error(f"解码URL时出错: {e}")
                    
                    # 检查订阅是否过期
                    # 添加isActive字段，与NodeJS实现保持一致
                    is_active = expire_at > now
                    
                    if is_active:
                        # 订阅有效，添加到列表
                        subscriptions.append({
                            'nft_mint_id': nft_mint_id,
                            'agent_url': agent_url,
                            'expire_at': expire_at,
                            'is_active': is_active,
                            'address': str(account_pubkey)  # 添加账户地址字段
                        })
                        logger.info(f"添加有效订阅: mint={nft_mint_id}, 过期时间={expire_at}")
                    else:
                        logger.debug(f"跳过已过期订阅: mint={nft_mint_id}, 过期时间={expire_at}")
                        
                except Exception as e:
                    logger.error(f"处理订阅账户数据时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue
            
            logger.info(f"获取到用户 {wallet_address} 的 {len(subscriptions)} 个有效NFT订阅")
            return subscriptions
            
        except Exception as e:
            logger.error(f"查询程序账户时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
            
    except Exception as e:
        logger.error(f"获取用户 {wallet_address} 的NFT订阅时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

async def get_nft_metadata_url_direct(rpc_url: str, agent_nft_pda: str) -> str:
    """
    直接使用HTTP请求获取NFT的元数据URL
    
    Args:
        rpc_url: Solana RPC URL
        agent_nft_pda: AgentNft PDA地址
        
    Returns:
        str: NFT的元数据URL
    """
    try:
        import json
        import requests
        import base64
        
        logger.debug(f"直接获取NFT {agent_nft_pda} 的元数据URL")
        
        # 构建RPC请求参数
        rpc_params = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [
                agent_nft_pda,
                {
                    "encoding": "base64"
                }
            ]
        }
        
        # 发送请求
        response = requests.post(rpc_url, json=rpc_params)
        
        if response.status_code != 200:
            logger.error(f"RPC请求失败: {response.text}")
            return "http://default-agent-url.com"
        
        # 解析响应
        result = response.json()
        
        if "result" not in result or result["result"] is None:
            logger.warning("RPC响应中没有result字段或result为空")
            return "http://default-agent-url.com"
        
        account_info = result["result"]["value"]
        
        if not account_info or "data" not in account_info:
            logger.warning("账户信息不包含数据")
            return "http://default-agent-url.com"
        
        # 获取数据
        data = account_info["data"]
        
        if not isinstance(data, list) or len(data) < 1:
            logger.warning(f"数据格式不正确: {data}")
            return "http://default-agent-url.com"
        
        # 解码Base64数据
        account_data = base64.b64decode(data[0])
        
        # 多种提取方法
        extracted_urls = []
        
        # 方法1: 使用特征提取 - 查找URL前缀
        try:
            # 解码整个账户数据，忽略错误
            data_str = account_data.decode('utf-8', errors='ignore')
            
            # 查找常见的URL前缀 (增加更多的前缀模式)
            for prefix in ['http://', 'https://', 'www.', 'HTTP://', 'HTTPS://']:
                index = data_str.find(prefix)
                if index >= 0:
                    # 找到URL前缀，提取URL直到遇到不可打印字符
                    url_start = index
                    url_end = url_start
                    
                    # 继续读取直到遇到不可见字符、空格或其他常见的URL结束符
                    while url_end < len(data_str) and data_str[url_end] >= ' ' and data_str[url_end] <= '~' and data_str[url_end] not in ['"', "'", '>', '<', ' ', '\t']:
                        url_end += 1
                    
                    raw_agent_url = data_str[url_start:url_end]
                    logger.debug(f"方法1提取到的URL: {raw_agent_url}")
                    
                    # URL长度不应该太短
                    if len(raw_agent_url) >= 10:
                        extracted_urls.append(raw_agent_url)
        except Exception as decode_error:
            logger.error(f"方法1解码失败: {decode_error}")
        
        # 方法2: Anchor账户结构解析
        try:
            # AgentNft预期结构: discriminator(8) + owner(32) + mint(32) + metadataUrl(string)
            # string格式: length(4 bytes) + 内容
            
            # 检查账户判别器
            discriminator = account_data[0:8].hex()
            
            # 从第72字节开始寻找字符串长度
            if len(account_data) >= 76:  # 至少有8+32+32+4=76字节
                str_len_bytes = account_data[72:76]
                str_len = int.from_bytes(str_len_bytes, byteorder='little')
                
                logger.debug(f"方法2解析的URL长度: {str_len}")
                
                # 验证长度是否合理 (比如小于1000且不超出数据长度)
                if 0 < str_len < 1000 and 76 + str_len <= len(account_data):
                    # 提取字符串内容
                    str_data = account_data[76:76+str_len]
                    try:
                        url = str_data.decode('utf-8', errors='replace')
                        logger.debug(f"方法2解析到的URL: {url}")
                        
                        # 长度应该合理
                        if len(url) >= 10:
                            extracted_urls.append(url)
                    except Exception as str_error:
                        logger.error(f"方法2解码URL失败: {str_error}")
        except Exception as struct_error:
            logger.error(f"方法2解析失败: {struct_error}")
            
        # 方法3: 启发式搜索 - 在整个数据中搜索可能的URL模式
        try:
            import re
            # 使用正则表达式查找URL模式
            # 包括HTTP/HTTPS URLs
            url_pattern = re.compile(rb'https?://[^\x00-\x20\x7F-\xFF]{3,}')
            urls = url_pattern.findall(account_data)
            
            for url_bytes in urls:
                try:
                    url = url_bytes.decode('utf-8', errors='replace')
                    logger.debug(f"方法3找到的URL: {url}")
                    if len(url) >= 10:
                        extracted_urls.append(url)
                except Exception as e:
                    logger.error(f"解码URL时出错: {e}")
        except Exception as regex_error:
            logger.error(f"方法3正则搜索失败: {regex_error}")
        
        # 处理提取的URL列表
        if extracted_urls:
            # 排序提取的URL，优先选择更长且看起来更有效的URL
            extracted_urls.sort(key=lambda x: (
                # 优先选择arweave.net和IPFS URLs
                1 if "arweave.net" in x.lower() else 
                (1 if "ipfs" in x.lower() else 0),
                # 然后按长度排序
                len(x)
            ), reverse=True)
            
            logger.info(f"找到{len(extracted_urls)}个候选URL，选择: {extracted_urls[0]}")
            return extracted_urls[0]
        
        # 所有方法都失败
        logger.warning("无法从账户数据中提取有效的元数据URL")
        return "http://default-agent-url.com"
        
    except Exception as e:
        logger.error(f"获取NFT元数据URL时出错: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        return "http://default-agent-url.com"

def validate_and_process_metadata_url(url: str) -> str:
    """
    验证并处理元数据URL
    
    Args:
        url: 原始元数据URL
        
    Returns:
        str: 处理后的有效URL
    """
    try:
        # 检查URL是否为空
        if not url or url.strip() == "":
            logger.warning("元数据URL为空")
            return "http://default-agent-url.com"
        
        # 规范化URL
        url = url.strip()
        
        # 处理以@开头的URL (如 @http://8.214.38.69:10003/.well-known/agent.json)
        if url.startswith("@http://") or url.startswith("@https://"):
            logger.debug(f"检测到以@开头的URL，移除前缀@")
            url = url[1:]  # 去掉@符号
        
        # 检查URL是否以http://或https://开头
        if not (url.startswith("http://") or url.startswith("https://")):
            logger.warning(f"元数据URL格式不正确，缺少http://或https://前缀: {url}")
            # 添加默认前缀
            url = "http://" + url
        
        # 处理URL中的非法字符
        from urllib.parse import urlparse, urlunparse
        
        # 解析URL
        try:
            parsed = urlparse(url)
            # 重新组装URL，确保格式正确
            url = urlunparse(parsed)
        except Exception as parse_error:
            logger.warning(f"URL解析错误: {parse_error}, 使用原始URL")
        
        # 检查是否是IP地址形式的URL (如http://8.214.38.69:10003/.well-known/agent.json)
        # 这种情况下保留原始URL
        import re
        if re.match(r'https?://\d+\.\d+\.\d+\.\d+(:\d+)?', url):
            logger.debug(f"检测到IP地址形式的URL")
            # 移除可能的.well-known/agent.json后缀，仅用于存储基本URL
            if "/.well-known/agent.json" in url:
                base_url = url.split("/.well-known/agent.json")[0]
                return base_url
            return url
            
        # 检查是否是arweave.net的URL，如果是则保留完整URL
        if "arweave.net" in url:
            logger.debug(f"检测到arweave.net URL")
            return url
            
        # 检查是否已包含.well-known/agent.json
        if "/.well-known/agent.json" in url:
            base_url = url.split("/.well-known/agent.json")[0]
            return base_url
        
        # 处理特殊情况：如果URL以大写HTTP开头
        if url.upper().startswith("HTTP://") and not url.startswith("http://"):
            url = "http://" + url[5:]
        elif url.upper().startswith("HTTPS://") and not url.startswith("https://"):
            url = "https://" + url[6:]
        
        # 确保URL不含空格
        url = url.replace(" ", "")
            
        # 其他情况，返回原始URL
        return url
        
    except Exception as e:
        logger.error(f"处理元数据URL时出错: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        return "http://default-agent-url.com" 