#!/usr/bin/env python
import sys
print(f"Python 版本: {sys.version}")
print(f"Python 路径: {sys.path}")

print("\n尝试导入Solana模块...")
try:
    from solders.pubkey import Pubkey
    print("- solders.pubkey.Pubkey 导入成功")
except ImportError as e:
    print(f"- solders.pubkey.Pubkey 导入失败: {e}")

try:
    from solders.signature import Signature
    print("- solders.signature 导入成功")
except ImportError as e:
    print(f"- solders.signature 导入失败: {e}")

try:
    from nacl.signing import VerifyKey
    print("- nacl.signing 导入成功")
except ImportError as e:
    print(f"- nacl.signing 导入失败: {e}")

print("\n显示已安装的包版本:")
try:
    import solana
    print(f"- solana: 版本 {solana.__version__ if hasattr(solana, '__version__') else '未知'}")
except ImportError as e:
    print(f"- solana: 导入失败 {e}")

try:
    import solders
    print(f"- solders: 版本 {solders.__version__ if hasattr(solders, '__version__') else '未知'}")
except ImportError as e:
    print(f"- solders: 导入失败 {e}")

try:
    import nacl
    print(f"- PyNaCl: 版本 {nacl.__version__ if hasattr(nacl, '__version__') else '未知'}")
except ImportError as e:
    print(f"- PyNaCl: 导入失败 {e}") 