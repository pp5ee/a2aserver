#!/usr/bin/env python
"""
MySQL数据库初始化脚本
用于创建A2A应用所需的数据库和表结构
"""
import os
import sys
import logging
import argparse
import pymysql

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def initialize_database(host="localhost", port=3306, user="root", password="orangepi123"):
    """初始化MySQL数据库和表结构"""
    
    try:
        # 首先尝试连接MySQL服务器（不指定数据库）
        logger.info(f"尝试连接MySQL服务器 {host}:{port}...")
        
        # 连接数据库服务器
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password
        )
        
        logger.info("连接成功，检查数据库...")
        cursor = conn.cursor()
        
        # 检查a2a数据库是否存在
        cursor.execute("SHOW DATABASES LIKE 'a2a'")
        exists = cursor.fetchone()
        
        if not exists:
        # 创建数据库
            logger.info("创建a2a数据库...")
            cursor.execute("CREATE DATABASE IF NOT EXISTS a2a")
            conn.commit()
            logger.info("a2a数据库创建成功")
        else:
            logger.info("a2a数据库已存在")
        
        # 选择a2a数据库
        cursor.execute("USE a2a")
        
        # 创建用户表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            wallet_address VARCHAR(255) PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        ''')
        
        # 创建用户代理关系表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_agents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            wallet_address VARCHAR(255),
            agent_url VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wallet_address) REFERENCES users(wallet_address) ON DELETE CASCADE,
            UNIQUE(wallet_address, agent_url)
        )
        ''')
        
        conn.commit()
        logger.info("数据库表结构初始化成功")
        
        cursor.close()
        conn.close()
        
        logger.info("数据库初始化完成")
        return True
        
    except pymysql.Error as err:
        logger.error(f"数据库初始化失败: {err}")
        return False

def main():
    """脚本主函数"""
    parser = argparse.ArgumentParser(description='初始化A2A应用的MySQL数据库')
    parser.add_argument('--host', default='localhost', help='MySQL主机地址')
    parser.add_argument('--port', default=3306, help='MySQL端口')
    parser.add_argument('--user', default='root', help='MySQL用户名')
    parser.add_argument('--password', default='orangepi123', help='MySQL密码')
    
    args = parser.parse_args()
    
    success = initialize_database(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password
    )
    
    if success:
        logger.info("✅ 数据库初始化成功！")
    else:
        logger.error("❌ 数据库初始化失败，请检查连接和权限！")

if __name__ == "__main__":
    main() 