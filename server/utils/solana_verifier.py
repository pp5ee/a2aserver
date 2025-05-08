import logging
import time
import base64
import datetime
from typing import Optional, Tuple, List, Dict, Any

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            
            self.logger.info(f"验证成功: public_key={public_key[:10]}..., nonce={nonce[:10]}...")
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
    从Solana区块链获取用户的NFT订阅状态
    
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
            
            # 尝试导入可能需要的类型
            try:
                from solana.rpc.types import MemcmpOpts
                has_memcmp_opts = True
                logger.info("成功导入MemcmpOpts类")
            except ImportError:
                has_memcmp_opts = False
                logger.info("无法导入MemcmpOpts类，将使用其他方式")
                
            try:
                from solana.rpc.core import Memcmp
                has_memcmp = True
                logger.info("成功导入Memcmp类")
            except ImportError:
                has_memcmp = False
                logger.info("无法导入Memcmp类，将使用其他方式")
        except ImportError as e:
            logger.error(f"导入模块失败: {e}")
            return []
        
        # 初始化Solana连接
        try:
            DEVNET_URL = 'https://api.devnet.solana.com'
            connection = Client(DEVNET_URL)
            logger.info(f"已连接到Solana节点: {DEVNET_URL}")
            
            # 打印SDK版本信息
            try:
                import solana
                logger.info(f"Solana SDK版本: {solana.__version__ if hasattr(solana, '__version__') else '未知'}")
            except:
                logger.info("无法获取Solana SDK版本")
        except Exception as e:
            logger.error(f"连接Solana节点失败: {e}")
            return []
        
        # 程序ID
        try:
            PROGRAM_ID = PublicKey.from_string('3Qqf9EXWLDhr9bzxdgUk6UQbDYuynAS5WKT5ygpYpQfQ')
            logger.info(f"使用程序ID: {PROGRAM_ID}")
        except Exception as e:
            logger.error(f"创建程序ID失败: {e}")
            return []
        
        # 将钱包地址转换为PublicKey
        try:
            user_pubkey = PublicKey.from_string(wallet_address)
            logger.info(f"用户公钥: {user_pubkey}")
            
            # 将用户公钥转换为base58编码
            user_pubkey_base58 = base58.b58encode(bytes(user_pubkey)).decode('utf-8')
            logger.info(f"用户公钥(base58): {user_pubkey_base58}")
        except Exception as e:
            logger.error(f"转换钱包地址失败: {e}")
            return []
        
        # 使用直接RPC调用获取用户订阅账户
        try:
            # 获取get_program_accounts方法的参数
            import inspect
            sig = inspect.signature(connection.get_program_accounts)
            param_names = [p for p in sig.parameters]
            logger.info(f"get_program_accounts方法参数: {param_names}")
            
            # 直接使用最基本的方式调用
            # 不使用复杂的过滤器参数，而是直接使用低级API
            try:
                # 构建RPC请求参数
                rpc_params = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getProgramAccounts",
                    "params": [
                        str(PROGRAM_ID),
                        {
                            "encoding": "base64",
                            "filters": [
                                {
                                    "memcmp": {
                                        "offset": 0,  # 账户判别器
                                        "bytes": "Bi9fTyJ7Nxx",  # Subscription账户判别器的base58编码
                                        "encoding": "base58"
                                    }
                                },
                                {
                                    "memcmp": {
                                        "offset": 8,  # 用户公钥
                                        "bytes": user_pubkey_base58
                                    }
                                }
                            ]
                        }
                    ]
                }
                
                # 直接使用底层HTTP请求
                import requests
                logger.info(f"发送直接RPC请求到 {DEVNET_URL}")
                logger.debug(f"请求参数: {json.dumps(rpc_params)}")
                
                response = requests.post(DEVNET_URL, json=rpc_params)
                logger.info(f"RPC响应状态码: {response.status_code}")
                
                if response.status_code != 200:
                    logger.error(f"RPC请求失败: {response.text}")
                    return []
                
                # 解析响应
                result = response.json()
                logger.debug(f"RPC响应: {json.dumps(result)}")
                
                if "result" not in result:
                    logger.warning("RPC响应中没有result字段")
                    return []
                
                accounts = result["result"]
                
                if not accounts:
                    logger.info("未找到任何账户")
                    return []
                    
                logger.info(f"找到 {len(accounts)} 个账户")
                
                # 解析账户数据
                subscriptions = []
                now = datetime.datetime.now()
                
                for account in accounts:
                    try:
                        # 检查账户数据格式
                        if "account" not in account or "pubkey" not in account:
                            logger.warning(f"账户格式不正确: {account}")
                            continue
                            
                        # 获取账户数据
                        account_info = account["account"]
                        pubkey = account["pubkey"]
                        
                        if "data" not in account_info:
                            logger.warning(f"账户信息格式不正确: {account_info}")
                            continue
                            
                        # 解析Base64编码的数据
                        data = account_info["data"]
                        
                        if not isinstance(data, list) or len(data) < 1:
                            logger.warning(f"数据格式不正确: {data}")
                            continue
                            
                        # 解码Base64数据
                        account_data = base64.b64decode(data[0])
                        
                        # 从账户数据中提取信息
                        if len(account_data) < 80:  # 确保数据长度足够
                            logger.warning(f"账户数据长度不足: {len(account_data)}")
                            continue
                            
                        # 添加更多日志用于调试
                        logger.info(f"账户数据总长度: {len(account_data)}")
                        logger.info(f"账户判别器(前8字节): {account_data[0:8].hex()}")
                        logger.info(f"用户公钥(8-40字节): {account_data[8:40].hex()}")
                        logger.info(f"NFT Mint(40-72字节): {account_data[40:72].hex()}")
                        
                        # 如果账户数据长度超过80字节，打印更多信息
                        if len(account_data) > 80:
                            logger.info(f"额外数据(80+字节): {account_data[80:min(100, len(account_data))].hex()}")
                        
                        user_data = account_data[8:40]
                        nft_mint_data = account_data[40:72]
                        user = str(PublicKey(user_data))
                        nft_mint_id = str(PublicKey(nft_mint_data))
                        try:
                            # 记录原始字节数据帮助调试
                            logger.info(f"原始时间戳字节: {account_data[72:80].hex()}")
                            
                            # 检查账户判别器，不同类型的账户可能有不同的数据结构
                            account_discriminator = account_data[0:8].hex()
                            logger.info(f"账户判别器: {account_discriminator}")
                            
                            # 根据账户判别器类型选择不同的解析方式
                            # 40071a8766846221 是Subscription账户的判别器
                            if account_discriminator == "40071a8766846221":
                                # 这是正确的Subscription账户，使用小端序解析时间戳
                                expires_at_seconds = int.from_bytes(account_data[72:80], byteorder='little')
                                logger.info(f"解析的过期时间戳(秒): {expires_at_seconds}")
                                
                                # 创建datetime对象
                                expire_at = datetime.datetime.fromtimestamp(expires_at_seconds)
                                logger.info(f"解析后的过期时间: {expire_at}")
                            else:
                                # 不是有效的Subscription账户，记录错误并跳过
                                logger.error(f"无效的账户判别器: {account_discriminator}，预期: 40071a8766846221")
                                continue
                        except Exception as e:
                            logger.error(f"解析时间戳出错: {e}")
                            continue  # 跳过此订阅
                        
                        logger.info(f"找到订阅: mint={nft_mint_id}, 过期时间={expire_at}")
                        
                        # 获取NFT的元数据URL
                        try:
                            # 计算AgentNft PDA - 使用另一种方式
                            try:
                                # 使用直接的RPC调用获取AgentNft账户
                                # 构建查询参数
                                rpc_params = {
                                    "jsonrpc": "2.0",
                                    "id": 1,
                                    "method": "getProgramAccounts",
                                    "params": [
                                        str(PROGRAM_ID),
                                        {
                                            "encoding": "base64",
                                            "filters": [
                                                {
                                                    "memcmp": {
                                                        "offset": 40,  # 跳过判别器(8字节)和owner(32字节)
                                                        "bytes": nft_mint_id
                                                    }
                                                }
                                            ]
                                        }
                                    ]
                                }
                                
                                # 发送请求
                                agent_response = requests.post(DEVNET_URL, json=rpc_params)
                                
                                if agent_response.status_code != 200:
                                    logger.error(f"获取AgentNft账户失败: {agent_response.text}")
                                    raw_agent_url = "http://default-agent-url.com"
                                else:
                                    # 解析响应
                                    agent_result = agent_response.json()
                                    
                                    if "result" not in agent_result or not agent_result["result"]:
                                        logger.warning("未找到AgentNft账户")
                                        raw_agent_url = "http://default-agent-url.com"
                                    else:
                                        # 获取第一个匹配的账户
                                        agent_account = agent_result["result"][0]
                                        agent_nft_pda = agent_account["pubkey"]
                                        
                                        # 获取元数据URL
                                        raw_agent_url = await get_nft_metadata_url_direct(DEVNET_URL, agent_nft_pda)
                            except Exception as pda_error:
                                logger.error(f"计算PDA失败: {pda_error}")
                                raw_agent_url = "http://default-agent-url.com"
                            
                            # 验证并处理元数据URL
                            agent_url = validate_and_process_metadata_url(raw_agent_url)
                            logger.info(f"处理后的元数据URL: {agent_url}")
                        except Exception as url_error:
                            logger.error(f"获取元数据URL失败: {url_error}")
                            agent_url = "http://default-agent-url.com"
                        
                        # 检查订阅是否过期
                        if expire_at > now:
                            subscriptions.append({
                                'nft_mint_id': nft_mint_id,
                                'agent_url': agent_url,
                                'expire_at': expire_at
                            })
                            logger.info(f"添加有效订阅: mint={nft_mint_id}, url={agent_url}, 过期时间={expire_at}")
                        else:
                            logger.info(f"跳过已过期订阅: mint={nft_mint_id}, 过期时间={expire_at}")
                    except Exception as e:
                        logger.error(f"解析账户数据时出错: {e}")
                        import traceback
                        logger.error(f"错误详情: {traceback.format_exc()}")
                        continue
                
                logger.info(f"获取到用户 {wallet_address} 的 {len(subscriptions)} 个有效NFT订阅")
                return subscriptions
                
            except Exception as direct_rpc_error:
                logger.error(f"直接RPC调用失败: {direct_rpc_error}")
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")
                return []
                
        except Exception as e:
            logger.error(f"获取程序账户时出错: {e}")
            # 打印更详细的错误信息
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return []
            
    except Exception as e:
        logger.error(f"获取用户 {wallet_address} 的NFT订阅状态时出错: {e}")
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
        
        logger.info(f"直接获取NFT {agent_nft_pda} 的元数据URL")
        
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
        
        logger.info(f"发送直接RPC请求获取账户信息")
        logger.debug(f"请求参数: {json.dumps(rpc_params)}")
        
        # 发送请求
        response = requests.post(rpc_url, json=rpc_params)
        logger.info(f"RPC响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"RPC请求失败: {response.text}")
            return "http://default-agent-url.com"
        
        # 解析响应
        result = response.json()
        logger.debug(f"RPC响应: {json.dumps(result)}")
        
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
        
        # 解析账户数据
        # 账户判别器 (8字节) + owner (32字节) + mint (32字节) + 字符串长度 (4字节) + 字符串内容
        fixed_fields_size = 8 + 32 + 32
        
        # 获取字符串长度
        if len(account_data) < fixed_fields_size + 4:
            logger.warning(f"账户数据长度不足: {len(account_data)}")
            return "http://default-agent-url.com"
            
        # 记录原始字节数据帮助调试
        logger.info(f"元数据URL长度字段(4字节): {account_data[fixed_fields_size:fixed_fields_size+4].hex()}")
        
        # 尝试解析字符串长度 - Solana/Rust使用小端序
        url_len = int.from_bytes(account_data[fixed_fields_size:fixed_fields_size+4], byteorder='little')
        logger.info(f"解析出的URL长度: {url_len}")
        
        # 检查URL长度是否合理
        if url_len > 1000 or fixed_fields_size + 4 + url_len > len(account_data):
            # 尝试直接从数据中提取URL
            try:
                # 查找URL特征，如"http"
                data_str = account_data[fixed_fields_size:].decode('utf-8', errors='ignore')
                http_index = data_str.find('http')
                if http_index >= 0:
                    # 提取URL直到第一个不可见字符
                    url_end = http_index
                    while url_end < len(data_str) and data_str[url_end] >= ' ' and data_str[url_end] <= '~':
                        url_end += 1
                    raw_agent_url = data_str[http_index:url_end]
                    logger.info(f"通过特征提取URL: {raw_agent_url}")
                    return raw_agent_url
            except Exception as extract_error:
                logger.error(f"尝试提取URL失败: {extract_error}")
            
            logger.warning(f"URL长度异常: {url_len}, 账户数据长度: {len(account_data)}")
            return "http://default-agent-url.com"
        
        # 获取元数据URL
        url_data = account_data[fixed_fields_size+4:fixed_fields_size+4+url_len]
        try:
            raw_agent_url = url_data.decode('utf-8')
            logger.info(f"从链上获取到原始元数据URL: {raw_agent_url}")
            return raw_agent_url
        except UnicodeDecodeError:
            # 如果解码失败，尝试查找http字符串
            logger.warning(f"URL解码失败，尝试查找http字符串")
            try:
                full_data = account_data[fixed_fields_size:].decode('utf-8', errors='ignore')
                http_index = full_data.find('http')
                if http_index >= 0:
                    # 提取URL直到第一个不可见字符
                    url_end = http_index
                    while url_end < len(full_data) and full_data[url_end] >= ' ' and full_data[url_end] <= '~':
                        url_end += 1
                    raw_agent_url = full_data[http_index:url_end]
                    logger.info(f"通过特征提取URL: {raw_agent_url}")
                    return raw_agent_url
            except Exception as e:
                logger.error(f"尝试提取URL失败: {e}")
            
            # 如果所有尝试都失败，返回默认URL
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
            logger.info(f"检测到以@开头的URL，移除前缀@: {url}")
            url = url[1:]  # 去掉@符号
        
        # 检查URL是否以http://或https://开头
        if not (url.startswith("http://") or url.startswith("https://")):
            logger.warning(f"元数据URL格式不正确，缺少http://或https://前缀: {url}")
            # 添加默认前缀
            url = "http://" + url
        
        # 检查是否是IP地址形式的URL (如http://8.214.38.69:10003/.well-known/agent.json)
        # 这种情况下保留原始URL
        import re
        if re.match(r'https?://\d+\.\d+\.\d+\.\d+(:\d+)?', url):
            logger.info(f"检测到IP地址形式的URL: {url}")
            # 移除可能的.well-known/agent.json后缀，仅用于存储基本URL
            if "/.well-known/agent.json" in url:
                base_url = url.split("/.well-known/agent.json")[0]
                logger.info(f"存储基本URL: {base_url}")
                return base_url
            return url
            
        # 检查是否是arweave.net的URL，如果是则保留
        if "arweave.net" in url:
            logger.info(f"检测到arweave.net URL: {url}")
            return url
            
        # 检查是否已包含.well-known/agent.json
        if "/.well-known/agent.json" in url:
            base_url = url.split("/.well-known/agent.json")[0]
            logger.info(f"从完整agent.json URL中提取基本URL: {base_url}")
            return base_url
            
        # 其他情况，返回原始URL
        return url
        
    except Exception as e:
        logger.error(f"处理元数据URL时出错: {e}")
        return "http://default-agent-url.com" 