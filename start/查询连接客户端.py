#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询 Stake 和 Winna WebSocket 连接的客户端列表
显示 username 和 IP 地址
"""
import os
import sys
import json
from datetime import datetime

# 动态修正路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 连接信息文件路径
STAKE_CONN_FILE = os.path.join(project_root, 'db', 'websocket_stake_connections.json')
WINNA_CONN_FILE = os.path.join(project_root, 'db', 'websocket_winna_connections.json')

def load_connections(conn_file):
    """加载连接信息"""
    if not os.path.exists(conn_file):
        return []
    try:
        with open(conn_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('connections', [])
    except Exception as e:
        return []

def format_connections(connections, service_name):
    """格式化并显示连接信息（按IP地址排序，相同IP放在一起）"""
    if not connections:
        print(f"\n{service_name}: 无连接")
        return
    
    # 按IP地址排序，相同IP放在一起
    sorted_connections = sorted(connections, key=lambda x: x.get('ip', ''))
    
    print(f"\n{service_name} 连接列表 (共 {len(sorted_connections)} 个):")
    print("=" * 100)
    print(f"{'序号':<6} {'Username':<20} {'用户标识':<12} {'IP 地址':<20} {'端口':<8} {'最后更新':<20}")
    print("-" * 100)
    
    for idx, conn in enumerate(sorted_connections, 1):
        username = conn.get('username', '-')
        user_id = conn.get('user_id', '-')
        ip = conn.get('ip', '-')
        port = conn.get('port', '-')
        last_update = conn.get('last_update', '-')
        
        # 格式化时间
        if last_update != '-':
            try:
                dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                last_update = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass
        
        print(f"{idx:<6} {username:<20} {user_id:<12} {ip:<20} {str(port):<8} {last_update:<20}")
    
    print("=" * 100)

def main():
    """主函数"""
    print("\n" + "=" * 100)
    print("WebSocket 客户端连接查询")
    print("=" * 100)
    
    # 加载 Stake 连接
    stake_connections = load_connections(STAKE_CONN_FILE)
    format_connections(stake_connections, "Stake")
    
    # 加载 Winna 连接
    winna_connections = load_connections(WINNA_CONN_FILE)
    format_connections(winna_connections, "Winna")
    
    # 统计信息
    total = len(stake_connections) + len(winna_connections)
    print(f"\n总计: {total} 个连接 (Stake: {len(stake_connections)}, Winna: {len(winna_connections)})")
    print()

if __name__ == '__main__':
    main()

