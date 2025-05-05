import logging
import time
import base64
from typing import Optional, Tuple

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