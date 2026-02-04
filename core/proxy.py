"""
代理配置模块
支持 SOCKS5, SOCKS4, HTTP 代理
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

# 全局代理配置
_proxy_config = {
    'enabled': False,
    'host': '127.0.0.1',
    'port': '1080',
    'type': 'SOCKS5'
}


def load_proxy_settings():
    """从配置文件加载代理设置"""
    global _proxy_config
    config_path = 'preferences.json'
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                _proxy_config = {
                    'enabled': settings.get('proxy_enabled', False),
                    'host': settings.get('proxy_host', '127.0.0.1'),
                    'port': settings.get('proxy_port', '1080'),
                    'type': settings.get('proxy_type', 'SOCKS5')
                }
                if _proxy_config['enabled']:
                    logger.info(f"Proxy loaded: {_proxy_config['type']}://{_proxy_config['host']}:{_proxy_config['port']}")
        except Exception as e:
            logger.error(f"Failed to load proxy settings: {e}")


def apply_proxy_settings(settings: dict):
    """应用代理设置"""
    global _proxy_config
    _proxy_config = {
        'enabled': settings.get('proxy_enabled', False),
        'host': settings.get('proxy_host', '127.0.0.1'),
        'port': settings.get('proxy_port', '1080'),
        'type': settings.get('proxy_type', 'SOCKS5')
    }
    if _proxy_config['enabled']:
        logger.info(f"Proxy applied: {_proxy_config['type']}://{_proxy_config['host']}:{_proxy_config['port']}")
    else:
        logger.info("Proxy disabled")


def get_proxies() -> dict:
    """获取 requests 库使用的代理字典"""
    if not _proxy_config['enabled']:
        return {}
    
    host = _proxy_config['host']
    port = _proxy_config['port']
    proxy_type = _proxy_config['type'].lower()
    
    if proxy_type == 'http':
        proxy_url = f'http://{host}:{port}'
    else:
        # socks5 or socks4
        proxy_url = f'{proxy_type}://{host}:{port}'
    
    return {
        'http': proxy_url,
        'https': proxy_url
    }


def is_proxy_enabled() -> bool:
    """检查代理是否启用"""
    return _proxy_config['enabled']


def get_proxy_url() -> str:
    """获取代理URL字符串"""
    if not _proxy_config['enabled']:
        return ''
    
    host = _proxy_config['host']
    port = _proxy_config['port']
    proxy_type = _proxy_config['type'].lower()
    
    if proxy_type == 'http':
        return f'http://{host}:{port}'
    else:
        return f'{proxy_type}://{host}:{port}'


# 启动时加载代理设置
load_proxy_settings()
