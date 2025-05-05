#!/usr/bin/env python
"""
A2A多用户测试脚本

使用不同的钱包地址测试多用户隔离功能。
确保服务器已经启动在12000端口。
"""

import requests
import json
import time
import sys

BASE_URL = "http://localhost:12000"

def print_colored(message, color="green"):
    """打印彩色文本"""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "end": "\033[0m",
    }
    
    print(f"{colors.get(color, colors['green'])}{message}{colors['end']}")

def make_request(endpoint, wallet_address, method="POST", data=None):
    """发送请求到服务器"""
    url = f"{BASE_URL}{endpoint}"
    headers = {"X-Solana-PublicKey": wallet_address}
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        else:
            response = requests.post(url, headers=headers, json=data)
        
        return response.json()
    except requests.exceptions.ConnectionError:
        print_colored(f"无法连接到服务器 {url}", "red")
        return None
    except json.JSONDecodeError:
        print_colored(f"无法解析服务器响应: {response.text}", "red")
        return None
    except Exception as e:
        print_colored(f"请求错误: {str(e)}", "red")
        return None

def check_server_status():
    """检查服务器状态"""
    print_colored("检查服务器状态...", "blue")
    
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print_colored(f"服务器状态: {data['status']}", "green")
            print_colored(f"多用户模式: {'启用' if data.get('multi_user', False) else '禁用'}", "green")
            return True
        else:
            print_colored(f"服务器状态码: {response.status_code}", "red")
            return False
    except requests.exceptions.ConnectionError:
        print_colored(f"无法连接到服务器，请确保服务器已启动在 {BASE_URL}", "red")
        return False
    except Exception as e:
        print_colored(f"检查服务器状态出错: {str(e)}", "red")
        return False

def register_agent(wallet_address, agent_url):
    """注册代理"""
    print_colored(f"用户 {wallet_address} 注册代理: {agent_url}...", "blue")
    
    result = make_request("/agent/register", wallet_address, data={"params": agent_url})
    
    if result is not None:
        print_colored(f"注册成功: {result}", "green")
        return True
    else:
        print_colored("注册失败", "red")
        return False

def list_agents(wallet_address):
    """列出代理"""
    print_colored(f"获取用户 {wallet_address} 的代理列表...", "blue")
    
    result = make_request("/agent/list", wallet_address, data={})
    
    if result is not None and "result" in result:
        agents = result["result"]
        if agents:
            for i, agent in enumerate(agents):
                print_colored(f"代理 {i+1}: {agent.get('name', 'Unknown')} - {agent.get('url', 'No URL')}", "cyan")
        else:
            print_colored("没有找到代理", "yellow")
        return agents
    else:
        print_colored("获取代理列表失败", "red")
        return []

def create_conversation(wallet_address):
    """创建会话"""
    print_colored(f"为用户 {wallet_address} 创建新会话...", "blue")
    
    result = make_request("/conversation/create", wallet_address, data={})
    
    if result is not None and "result" in result:
        conversation = result["result"]
        print_colored(f"会话创建成功，ID: {conversation.get('conversation_id', 'Unknown')}", "green")
        return conversation
    else:
        print_colored("创建会话失败", "red")
        return None

def list_conversations(wallet_address):
    """列出会话"""
    print_colored(f"获取用户 {wallet_address} 的会话列表...", "blue")
    
    result = make_request("/conversation/list", wallet_address, data={})
    
    if result is not None and "result" in result:
        conversations = result["result"]
        if conversations:
            for i, conv in enumerate(conversations):
                print_colored(f"会话 {i+1}: {conv.get('conversation_id', 'Unknown')}", "cyan")
        else:
            print_colored("没有找到会话", "yellow")
        return conversations
    else:
        print_colored("获取会话列表失败", "red")
        return []

def run_multi_user_test():
    """运行多用户测试"""
    print_colored("=" * 60, "magenta")
    print_colored("开始A2A多用户功能测试", "magenta")
    print_colored("=" * 60, "magenta")
    
    # 检查服务器状态
    if not check_server_status():
        return
    
    # 定义测试用户
    user1 = "wallet_address_user1"
    user2 = "wallet_address_user2"
    
    print_colored("\n[第1步] 测试不同用户的代理隔离", "magenta")
    
    # 用户1注册代理
    register_agent(user1, "http://agent1.example.com")
    register_agent(user1, "http://agent2.example.com")
    
    # 用户2注册代理
    register_agent(user2, "http://agent3.example.com")
    
    # 列出用户1的代理
    print_colored("\n用户1的代理列表:", "yellow")
    user1_agents = list_agents(user1)
    
    # 列出用户2的代理
    print_colored("\n用户2的代理列表:", "yellow")
    user2_agents = list_agents(user2)
    
    # 验证代理隔离
    if len(user1_agents) == 2 and len(user2_agents) == 1:
        print_colored("\n✅ 代理隔离测试通过!", "green")
    else:
        print_colored("\n❌ 代理隔离测试失败!", "red")
    
    print_colored("\n[第2步] 测试不同用户的会话隔离", "magenta")
    
    # 用户1创建2个会话
    create_conversation(user1)
    create_conversation(user1)
    
    # 用户2创建1个会话
    create_conversation(user2)
    
    # 列出用户1的会话
    print_colored("\n用户1的会话列表:", "yellow")
    user1_convs = list_conversations(user1)
    
    # 列出用户2的会话
    print_colored("\n用户2的会话列表:", "yellow")
    user2_convs = list_conversations(user2)
    
    # 验证会话隔离
    if len(user1_convs) == 2 and len(user2_convs) == 1:
        print_colored("\n✅ 会话隔离测试通过!", "green")
    else:
        print_colored("\n❌ 会话隔离测试失败!", "red")
    
    print_colored("\n测试完成，查看上方结果确认多用户隔离功能是否正常工作。", "magenta")

if __name__ == "__main__":
    run_multi_user_test() 