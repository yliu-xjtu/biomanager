import os
import hashlib
import logging
import json
from typing import List, Dict, Tuple, Optional
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_excluded_folders() -> List[str]:
    """从配置文件读取排除的文件夹列表"""
    config_path = 'preferences.json'
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                return settings.get('excluded_folders', [])
        except Exception as e:
            logger.warning(f"Failed to read excluded folders from config: {e}")
    return []


def is_path_excluded(path: str, root_dir: str, excluded_folders: List[str]) -> bool:
    """检查路径是否在排除列表中"""
    if not excluded_folders:
        return False
    
    # 获取相对于根目录的路径
    try:
        rel_path = os.path.relpath(path, root_dir)
        # 统一使用正斜杠
        rel_path = rel_path.replace('\\', '/')
        
        for excluded in excluded_folders:
            excluded = excluded.replace('\\', '/')
            # 检查路径是否以排除文件夹开头
            if rel_path == excluded or rel_path.startswith(excluded + '/'):
                return True
    except ValueError:
        # 在不同驱动器上时relpath会抛出异常
        pass
    
    return False


def compute_sha256(file_path: str) -> str:
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Failed to compute hash for {file_path}: {e}")
        raise

def scan_directory(root_dir: str, extensions: tuple = ('.pdf', '.PDF', '.png', '.jpg', '.jpeg', '.bmp', '.tiff'), excluded_folders: List[str] = None) -> List[str]:
    """
    扫描目录中的文件
    
    Args:
        root_dir: 根目录路径
        extensions: 要扫描的文件扩展名
        excluded_folders: 要排除的文件夹列表（相对于root_dir的路径）
                         如果为None，则从配置文件读取
    
    Returns:
        找到的文件路径列表
    """
    files = []
    
    # 如果没有传入排除列表，从配置文件读取
    if excluded_folders is None:
        excluded_folders = get_excluded_folders()
    
    # 记录排除的文件夹
    if excluded_folders:
        logger.info(f"Excluded folders: {excluded_folders}")
    
    try:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # 检查当前目录是否应该被排除
            if is_path_excluded(dirpath, root_dir, excluded_folders):
                # 清空dirnames以阻止os.walk进入子目录
                dirnames.clear()
                logger.debug(f"Skipping excluded directory: {dirpath}")
                continue
            
            # 从dirnames中移除排除的子目录，防止os.walk进入
            dirs_to_remove = []
            for dirname in dirnames:
                subdir_path = os.path.join(dirpath, dirname)
                if is_path_excluded(subdir_path, root_dir, excluded_folders):
                    dirs_to_remove.append(dirname)
            for dirname in dirs_to_remove:
                dirnames.remove(dirname)
                logger.debug(f"Skipping excluded subdirectory: {dirname}")
            
            for filename in filenames:
                if filename.lower().endswith(extensions):
                    full_path = os.path.join(dirpath, filename)
                    files.append(full_path)
        
        logger.info(f"Found {len(files)} files in {root_dir}")
    except Exception as e:
        logger.error(f"Error scanning directory {root_dir}: {e}")
    return files

def get_file_info(file_path: str) -> Dict[str, any]:
    try:
        stat = os.stat(file_path)
        filename = os.path.basename(file_path)
        return {
            'path': file_path,
            'filename': filename,
            'size': stat.st_size,
            'mtime': stat.st_mtime,
            'sha256': compute_sha256(file_path)
        }
    except Exception as e:
        logger.error(f"Failed to get file info for {file_path}: {e}")
        return {
            'path': file_path,
            'filename': os.path.basename(file_path) if file_path else '',
            'size': 0,
            'mtime': 0,
            'sha256': '',
            'error': str(e)
        }

def compare_file_changes(existing_info: Dict, new_info: Dict) -> bool:
    return (existing_info.get('sha256') != new_info.get('sha256') or
            existing_info.get('size') != new_info.get('size') or
            existing_info.get('mtime') != new_info.get('mtime'))
