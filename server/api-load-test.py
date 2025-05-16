#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import websocket
import threading
import time
import argparse
import json
import random
import logging
from concurrent.futures import ThreadPoolExecutor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def truncate_text(text, max_length=100):
    """截断长文本，超过指定长度时添加省略号"""
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=False)
    text = str(text)
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text

class LoadTester:
    def __init__(self, base_url, ws_url, headers, http_threads, http_ramp_time, ws_connections, ws_ramp_time):
        self.base_url = base_url
        self.ws_url = ws_url
        self.headers = headers
        self.http_threads = http_threads
        self.http_ramp_time = http_ramp_time
        self.ws_connections = ws_connections
        self.ws_ramp_time = ws_ramp_time
        self.conversation_ids = []
        self.stats = {
            'conversation_list_times': [],
            'task_list_times': [],
            'message_list_times': [],
            'ws_connect_times': [],
            'errors': 0,
            'success_requests': 0,  # 成功请求总数
            'requests_with_data': 0,  # 获取到数据的请求数
            'failed_requests': 0,  # 失败的请求数
            'status_codes': {}  # 按响应码分类的请求数量
        }
        self.ws_clients = []
        self.running = True

    def fetch_conversation_list(self):
        start_time = time.time()
        try:
            # 打印请求信息
            url = f"{self.base_url}/conversation/list"
            payload = {}
            logger.info(f"请求: POST {url} - 载荷: {truncate_text(payload)}")
            
            response = requests.post(url, headers=self.headers, json=payload)
            
            # 记录状态码统计
            status_code = response.status_code
            if status_code not in self.stats['status_codes']:
                self.stats['status_codes'][status_code] = 0
            self.stats['status_codes'][status_code] += 1
            
            # 打印响应信息
            try:
                response_data = response.json()
                logger.info(f"响应: {status_code} - 内容: {truncate_text(response_data)}")
            except:
                logger.info(f"响应: {status_code} - 内容: {truncate_text(response.text)}")
            
            response.raise_for_status()
            elapsed = time.time() - start_time
            self.stats['conversation_list_times'].append(elapsed)
            self.stats['success_requests'] += 1
            
            # 从响应中获取对话列表
            result = response.json().get('result', [])
            if result:
                self.stats['requests_with_data'] += 1
                # 随机选择一个对话ID
                conversation = random.choice(result)
                conversation_id = conversation.get('conversation_id')
                if conversation_id:
                    self.conversation_ids.append(conversation_id)
                    return conversation_id
            logger.warning("No conversations found")
            return None
        except Exception as e:
            self.stats['errors'] += 1
            self.stats['failed_requests'] += 1
            logger.error(f"Error fetching conversation list: {str(e)}")
            return None

    def create_conversation(self):
        """创建一个新的对话"""
        logger.info("创建新对话")
        try:
            # 打印请求信息
            url = f"{self.base_url}/conversation/create"
            payload = {}
            logger.info(f"请求: POST {url} - 载荷: {truncate_text(payload)}")
            
            response = requests.post(
                url, 
                headers=self.headers,
                json=payload
            )
            
            # 记录状态码统计
            status_code = response.status_code
            if status_code not in self.stats['status_codes']:
                self.stats['status_codes'][status_code] = 0
            self.stats['status_codes'][status_code] += 1
            
            # 打印响应信息
            try:
                response_data = response.json()
                logger.info(f"响应: {status_code} - 内容: {truncate_text(response_data)}")
            except:
                logger.info(f"响应: {status_code} - 内容: {truncate_text(response.text)}")
            
            response.raise_for_status()
            self.stats['success_requests'] += 1
            
            # 从响应中获取新创建的对话ID
            result = response.json().get('result', {})
            if result:
                self.stats['requests_with_data'] += 1
                
            conversation_id = result.get('conversation_id')
            
            if conversation_id:
                logger.info(f"创建了新对话: {conversation_id}")
                self.conversation_ids.append(conversation_id)
                return conversation_id
            else:
                logger.error("创建对话失败: 响应中没有对话ID")
                return None
        except Exception as e:
            self.stats['errors'] += 1
            self.stats['failed_requests'] += 1
            logger.error(f"创建对话时出错: {str(e)}")
            return None

    def fetch_task_list(self, conversation_id):
        if not conversation_id:
            return
        
        start_time = time.time()
        try:
            # 获取任务列表
            url = f"{self.base_url}/task/list"
            payload = {"conversation_id": conversation_id}
            logger.info(f"请求: POST {url} - 载荷: {truncate_text(payload)}")
            
            task_response = requests.post(
                url, 
                headers=self.headers, 
                json=payload
            )
            
            # 记录状态码统计
            status_code = task_response.status_code
            if status_code not in self.stats['status_codes']:
                self.stats['status_codes'][status_code] = 0
            self.stats['status_codes'][status_code] += 1
            
            # 打印响应信息
            try:
                response_data = task_response.json()
                logger.info(f"响应: {status_code} - 内容: {truncate_text(response_data)}")
            except:
                logger.info(f"响应: {status_code} - 内容: {truncate_text(task_response.text)}")
                response_data = {}
            
            task_response.raise_for_status()
            elapsed = time.time() - start_time
            self.stats['task_list_times'].append(elapsed)
            self.stats['success_requests'] += 1
            
            # 处理响应
            tasks = response_data.get('result', [])
            if tasks:
                self.stats['requests_with_data'] += 1
                logger.info(f"获取到 {len(tasks)} 个任务")
            else:
                logger.info("没有获取到任务")
        except Exception as e:
            self.stats['errors'] += 1
            self.stats['failed_requests'] += 1
            logger.error(f"获取任务列表时出错: {str(e)}")

    def fetch_message_list(self, conversation_id):
        if not conversation_id:
            return
        
        start_time = time.time()
        try:
            # 获取消息列表
            url = f"{self.base_url}/message/list"
            payload = {"params": conversation_id}
            logger.info(f"请求: POST {url} - 载荷: {truncate_text(payload)}")
            
            message_response = requests.post(
                url, 
                headers=self.headers, 
                json=payload
            )
            
            # 记录状态码统计
            status_code = message_response.status_code
            if status_code not in self.stats['status_codes']:
                self.stats['status_codes'][status_code] = 0
            self.stats['status_codes'][status_code] += 1
            
            # 打印响应信息
            try:
                response_data = message_response.json()
                logger.info(f"响应: {status_code} - 内容: {truncate_text(response_data)}")
            except:
                logger.info(f"响应: {status_code} - 内容: {truncate_text(message_response.text)}")
                response_data = {}
            
            message_response.raise_for_status()
            elapsed = time.time() - start_time
            self.stats['message_list_times'].append(elapsed)
            self.stats['success_requests'] += 1
            
            # 处理响应
            messages = response_data.get('result', [])
            if messages:
                self.stats['requests_with_data'] += 1
                logger.info(f"获取到 {len(messages)} 条消息，对话ID: {conversation_id}")
            else:
                logger.info(f"没有获取到消息，对话ID: {conversation_id}")
                
        except Exception as e:
            self.stats['errors'] += 1
            self.stats['failed_requests'] += 1
            logger.error(f"获取消息列表时出错: {str(e)}")

    def send_message(self, conversation_id):
        """向对话发送测试消息"""
        if not conversation_id:
            return
            
        try:
            # 准备消息内容
            message_content = f"Test message {time.time()}"
            
            # 构建消息请求体
            message_data = {
                "params": {
                    "role": "user",
                    "content": message_content,
                    "parts": [
                        {"type": "text", "text": message_content}
                    ],
                    "metadata": {
                        "conversation_id": conversation_id
                    }
                }
            }
            
            # 发送消息
            url = f"{self.base_url}/message/send"
            logger.info(f"请求: POST {url} - 载荷: {truncate_text(message_data)}")
            
            start_time = time.time()
            send_response = requests.post(
                url,
                headers=self.headers,
                json=message_data
            )
            
            # 记录状态码统计
            status_code = send_response.status_code
            if status_code not in self.stats['status_codes']:
                self.stats['status_codes'][status_code] = 0
            self.stats['status_codes'][status_code] += 1
            
            # 打印响应信息
            try:
                response_data = send_response.json()
                logger.info(f"响应: {status_code} - 内容: {truncate_text(response_data)}")
            except:
                logger.info(f"响应: {status_code} - 内容: {truncate_text(send_response.text)}")
            
            send_response.raise_for_status()
            elapsed = time.time() - start_time
            self.stats['success_requests'] += 1
            
            # 记录统计信息
            if 'send_message_times' not in self.stats:
                self.stats['send_message_times'] = []
            self.stats['send_message_times'].append(elapsed)
            
            # 处理响应
            result = send_response.json().get('result', {})
            if result:
                self.stats['requests_with_data'] += 1
                
            message_id = result.get('message_id')
            logger.debug(f"发送消息成功，ID: {message_id}")
            return message_id
        except Exception as e:
            self.stats['errors'] += 1
            self.stats['failed_requests'] += 1
            logger.error(f"发送消息时出错: {str(e)}")
            return None

    def run_http_thread(self):
        # 首先获取对话列表
        conversation_id = None
        try:
            # 获取conversation list
            url = f"{self.base_url}/conversation/list"
            payload = {}
            logger.info(f"请求: POST {url} - 载荷: {truncate_text(payload)}")
            
            conversation_list_response = requests.post(
                url, 
                headers=self.headers, 
                json=payload
            )
            
            # 记录状态码统计
            status_code = conversation_list_response.status_code
            if status_code not in self.stats['status_codes']:
                self.stats['status_codes'][status_code] = 0
            self.stats['status_codes'][status_code] += 1
            
            # 打印响应信息
            try:
                response_data = conversation_list_response.json()
                logger.info(f"响应: {status_code} - 内容: {truncate_text(response_data)}")
            except:
                logger.info(f"响应: {status_code} - 内容: {truncate_text(conversation_list_response.text)}")
            
            conversation_list_response.raise_for_status()
            self.stats['success_requests'] += 1
            
            # 从响应中获取对话列表
            result = response_data.get('result', [])
            if result:
                self.stats['requests_with_data'] += 1
                # 随机选择一个对话ID
                conversation = random.choice(result)
                conversation_id = conversation.get('conversation_id')
                logger.info(f"使用现有对话: {conversation_id}")
            else:
                logger.warning("未找到现有对话，创建新对话")
                # 如果没有现有对话，创建一个新对话
                url = f"{self.base_url}/conversation/create"
                payload = {}
                logger.info(f"请求: POST {url} - 载荷: {truncate_text(payload)}")
                
                create_response = requests.post(
                    url, 
                    headers=self.headers,
                    json=payload
                )
                
                # 记录状态码统计
                status_code = create_response.status_code
                if status_code not in self.stats['status_codes']:
                    self.stats['status_codes'][status_code] = 0
                self.stats['status_codes'][status_code] += 1
                
                # 打印响应信息
                try:
                    response_data = create_response.json()
                    logger.info(f"响应: {status_code} - 内容: {truncate_text(response_data)}")
                except:
                    logger.info(f"响应: {status_code} - 内容: {truncate_text(create_response.text)}")
                
                create_response.raise_for_status()
                self.stats['success_requests'] += 1
                
                # 从响应中获取新创建的对话ID
                result = create_response.json().get('result', {})
                if result:
                    self.stats['requests_with_data'] += 1
                    conversation_id = result.get('conversation_id')
                    logger.info(f"创建了新对话: {conversation_id}")
        except Exception as e:
            self.stats['errors'] += 1
            self.stats['failed_requests'] += 1
            logger.error(f"获取/创建对话时出错: {str(e)}")
            
        # 如果有对话ID，继续执行后续逻辑
        if conversation_id:
            self.conversation_ids.append(conversation_id)
            
            # 发送一条测试消息
            try:
                # 准备消息内容
                message_content = f"Test message {time.time()}"
                
                # 构建消息请求体
                message_data = {
                    "params": {
                        "role": "user",
                        "content": message_content,
                        "parts": [
                            {"type": "text", "text": message_content}
                        ],
                        "metadata": {
                            "conversation_id": conversation_id
                        }
                    }
                }
                
                # 发送消息
                url = f"{self.base_url}/message/send"
                logger.info(f"请求: POST {url} - 载荷: {truncate_text(message_data)}")
                
                start_time = time.time()
                send_response = requests.post(
                    url,
                    headers=self.headers,
                    json=message_data
                )
                
                # 记录状态码统计
                status_code = send_response.status_code
                if status_code not in self.stats['status_codes']:
                    self.stats['status_codes'][status_code] = 0
                self.stats['status_codes'][status_code] += 1
                
                # 打印响应信息
                try:
                    response_data = send_response.json()
                    logger.info(f"响应: {status_code} - 内容: {truncate_text(response_data)}")
                except:
                    logger.info(f"响应: {status_code} - 内容: {truncate_text(send_response.text)}")
                
                send_response.raise_for_status()
                elapsed = time.time() - start_time
                self.stats['success_requests'] += 1
                
                # 记录统计信息
                if 'send_message_times' not in self.stats:
                    self.stats['send_message_times'] = []
                self.stats['send_message_times'].append(elapsed)
                
                logger.info(f"消息发送成功到对话: {conversation_id}")
            except Exception as e:
                self.stats['errors'] += 1
                self.stats['failed_requests'] += 1
                logger.error(f"发送消息时出错: {str(e)}")
            
            # 获取任务列表
            try:
                url = f"{self.base_url}/task/list"
                payload = {"conversation_id": conversation_id}
                logger.info(f"请求: POST {url} - 载荷: {truncate_text(payload)}")
                
                task_response = requests.post(
                    url, 
                    headers=self.headers, 
                    json=payload
                )
                
                # 记录状态码统计
                status_code = task_response.status_code
                if status_code not in self.stats['status_codes']:
                    self.stats['status_codes'][status_code] = 0
                self.stats['status_codes'][status_code] += 1
                
                # 打印响应信息
                try:
                    response_data = task_response.json()
                    logger.info(f"响应: {status_code} - 内容: {truncate_text(response_data)}")
                except:
                    logger.info(f"响应: {status_code} - 内容: {truncate_text(task_response.text)}")
                
                task_response.raise_for_status()
                self.stats['success_requests'] += 1
                
                # 处理响应
                tasks = response_data.get('result', [])
                if tasks:
                    self.stats['requests_with_data'] += 1
                    logger.info(f"获取到 {len(tasks)} 个任务")
                else:
                    logger.info("没有获取到任务")
            except Exception as e:
                self.stats['errors'] += 1
                self.stats['failed_requests'] += 1
                logger.error(f"获取任务列表时出错: {str(e)}")
            
            # 获取消息列表
            try:
                url = f"{self.base_url}/message/list"
                payload = {"params": conversation_id}
                logger.info(f"请求: POST {url} - 载荷: {truncate_text(payload)}")
                
                message_response = requests.post(
                    url, 
                    headers=self.headers, 
                    json=payload
                )
                
                # 记录状态码统计
                status_code = message_response.status_code
                if status_code not in self.stats['status_codes']:
                    self.stats['status_codes'][status_code] = 0
                self.stats['status_codes'][status_code] += 1
                
                # 打印响应信息
                try:
                    response_data = message_response.json()
                    logger.info(f"响应: {status_code} - 内容: {truncate_text(response_data)}")
                except:
                    logger.info(f"响应: {status_code} - 内容: {truncate_text(message_response.text)}")
                
                message_response.raise_for_status()
                self.stats['success_requests'] += 1
                
                # 处理响应
                messages = response_data.get('result', [])
                if messages:
                    self.stats['requests_with_data'] += 1
                    logger.info(f"获取到 {len(messages)} 条消息，对话ID: {conversation_id}")
                else:
                    logger.info(f"没有获取到消息，对话ID: {conversation_id}")
            except Exception as e:
                self.stats['errors'] += 1
                self.stats['failed_requests'] += 1
                logger.error(f"获取消息列表时出错: {str(e)}")
        else:
            logger.error("无法获取或创建对话，无法继续执行后续操作")

    def on_ws_message(self, ws, message):
        logger.debug(f"WebSocket received: {message[:100]}...")

    def on_ws_error(self, ws, error):
        self.stats['errors'] += 1
        logger.error(f"WebSocket error: {str(error)}")

    def on_ws_close(self, ws, close_status_code, close_msg):
        logger.debug("WebSocket connection closed")

    def on_ws_open(self, ws):
        logger.debug("WebSocket connection established")

    def create_ws_connection(self):
        try:
            start_time = time.time()
            
            # 转换headers为WebSocket兼容格式
            ws_headers = []
            for key, value in self.headers.items():
                ws_headers.append(f"{key}: {value}")
            
            ws = websocket.WebSocketApp(
                self.ws_url,
                header=ws_headers,
                on_open=self.on_ws_open,
                on_message=self.on_ws_message,
                on_error=self.on_ws_error,
                on_close=self.on_ws_close
            )
            
            self.ws_clients.append(ws)
            elapsed = time.time() - start_time
            self.stats['ws_connect_times'].append(elapsed)
            
            # 在新线程中运行WebSocket连接
            threading.Thread(target=ws.run_forever).start()
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"Error creating WebSocket connection: {str(e)}")

    def start_http_load_test(self):
        logger.info(f"Starting HTTP load test with {self.http_threads} threads over {self.http_ramp_time} seconds")
        delay = self.http_ramp_time / self.http_threads if self.http_threads > 0 else 0
        
        with ThreadPoolExecutor(max_workers=self.http_threads) as executor:
            for i in range(self.http_threads):
                executor.submit(self.run_http_thread)
                time.sleep(delay)

    def start_ws_load_test(self):
        logger.info(f"Starting WebSocket load test with {self.ws_connections} connections over {self.ws_ramp_time} seconds")
        delay = self.ws_ramp_time / self.ws_connections if self.ws_connections > 0 else 0
        
        for i in range(self.ws_connections):
            threading.Thread(target=self.create_ws_connection).start()
            time.sleep(delay)

    def print_stats(self):
        logger.info("\n--- Test Results ---")
        
        # 请求成功率统计
        total_requests = self.stats['success_requests'] + self.stats['failed_requests']
        success_rate = (self.stats['success_requests'] / total_requests * 100) if total_requests > 0 else 0
        data_rate = (self.stats['requests_with_data'] / total_requests * 100) if total_requests > 0 else 0
        
        logger.info(f"总请求数: {total_requests}")
        logger.info(f"成功请求数: {self.stats['success_requests']} ({success_rate:.2f}%)")
        logger.info(f"获取到数据的请求数: {self.stats['requests_with_data']} ({data_rate:.2f}%)")
        logger.info(f"失败请求数: {self.stats['failed_requests']}")
        
        # 按状态码统计
        logger.info("\n状态码统计:")
        for status_code, count in sorted(self.stats['status_codes'].items()):
            status_type = "成功" if 200 <= status_code < 300 else "失败"
            logger.info(f"  {status_code} ({status_type}): {count} 次")
        
        # 响应时间统计
        logger.info("\n响应时间统计:")
        if self.stats['conversation_list_times']:
            avg_conv = sum(self.stats['conversation_list_times']) / len(self.stats['conversation_list_times'])
            logger.info(f"对话列表 API - 平均响应时间: {avg_conv:.4f}s")
        
        if self.stats['task_list_times']:
            avg_task = sum(self.stats['task_list_times']) / len(self.stats['task_list_times'])
            logger.info(f"任务列表 API - 平均响应时间: {avg_task:.4f}s")
        
        if self.stats['message_list_times']:
            avg_msg = sum(self.stats['message_list_times']) / len(self.stats['message_list_times'])
            logger.info(f"消息列表 API - 平均响应时间: {avg_msg:.4f}s")
            
        if 'send_message_times' in self.stats and self.stats['send_message_times']:
            avg_send = sum(self.stats['send_message_times']) / len(self.stats['send_message_times'])
            logger.info(f"发送消息 API - 平均响应时间: {avg_send:.4f}s")
        
        if self.stats['ws_connect_times']:
            avg_ws = sum(self.stats['ws_connect_times']) / len(self.stats['ws_connect_times'])
            logger.info(f"WebSocket 连接 - 平均连接时间: {avg_ws:.4f}s")
        
        logger.info(f"\n总错误数: {self.stats['errors']}")
        logger.info("--- End Results ---\n")

    def run(self):
        # 启动HTTP测试
        self.start_http_load_test()
        
        # 启动WebSocket测试
        self.start_ws_load_test()
        
        # 等待HTTP测试完成
        time.sleep(5)
        
        # 打印统计信息
        self.print_stats()
        
        # 保持WebSocket连接，直到用户按Ctrl+C
        logger.info("WebSocket connections active. Press Ctrl+C to stop.")
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.running = False
        logger.info("Closing WebSocket connections...")
        for ws in self.ws_clients:
            ws.close()

def main():
    parser = argparse.ArgumentParser(description='Load testing tool for server APIs and WebSocket')
    
    parser.add_argument('--base-url', type=str, default='http://localhost:12000',
                        help='Base URL for HTTP API requests')
    parser.add_argument('--ws-url', type=str, default='ws://localhost:12000/api/ws',
                        help='WebSocket URL')
    
    parser.add_argument('--nonce', type=str, default='1747979511344',
                        help='x-solana-nonce header value')
    parser.add_argument('--public-key', type=str, 
                        default='CdRe7WEGw2T1tuWCwq8zB6Q76XicMfDCN5SBL3BQgpp1',
                        help='x-solana-publickey header value')
    parser.add_argument('--signature', type=str, 
                        default='d0s6XFEh29ltJAawZrFmMzCSwsoB9zJpjoR5FB/ackTFJ0adlgCVAdU7rCkFQ/Q0dbGSlN8EeVy8r2q/Q5t3Dw==',
                        help='x-solana-signature header value')
    
    parser.add_argument('--http-threads', type=int, default=10,
                        help='Number of HTTP request threads')
    parser.add_argument('--http-ramp-time', type=int, default=5,
                        help='Time in seconds to ramp up HTTP threads')
    
    parser.add_argument('--ws-connections', type=int, default=5,
                        help='Number of WebSocket connections')
    parser.add_argument('--ws-ramp-time', type=int, default=3,
                        help='Time in seconds to ramp up WebSocket connections')
    
    args = parser.parse_args()
    
    # 准备请求头
    headers = {
        'X-Solana-Nonce': args.nonce,
        'X-Solana-PublicKey': args.public_key,
        'X-Solana-Signature': args.signature,
    }
    
    # 创建并运行测试
    tester = LoadTester(
        base_url=args.base_url,
        ws_url=args.ws_url,
        headers=headers,
        http_threads=args.http_threads,
        http_ramp_time=args.http_ramp_time,
        ws_connections=args.ws_connections,
        ws_ramp_time=args.ws_ramp_time
    )
    
    tester.run()

if __name__ == "__main__":
    main()
#python3 api-load-test.py --base-url https://agenticdao.net/beapi --ws-url wss://agenticdao.net/api/ws --http-threads 50 --ws-connections 1 