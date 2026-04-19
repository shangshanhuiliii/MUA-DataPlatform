import re
from typing import Any, Dict, List, Optional
from pathlib import Path
import logging

from ..config import Config

logger = logging.getLogger(__name__)

class ValidationUtils:
    """数据验证工具类"""
    
    @staticmethod
    def validate_event_type(event_type: str) -> bool:
        """验证事件类型是否有效"""
        return Config.validate_event_type(event_type)
    
    @staticmethod
    def validate_dataset_name(dataset_name: str) -> bool:
        """验证数据集名称是否有效"""
        if not dataset_name or not isinstance(dataset_name, str):
            return False
        
        # 检查是否包含非法字符
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        if any(char in dataset_name for char in invalid_chars):
            return False
        
        # 检查长度
        if len(dataset_name) < 1 or len(dataset_name) > 100:
            return False
        
        return True
    
    @staticmethod
    def validate_device_serial(serial: str) -> bool:
        """验证设备序列号格式"""
        if not serial or not isinstance(serial, str):
            return False
        
        # 基本格式检查，允许字母、数字、连字符、冒号、点号（支持IP:port格式）
        pattern = r'^[a-zA-Z0-9\-:.]+$'
        return bool(re.match(pattern, serial))
    
    @staticmethod
    def validate_package_name(package_name: str) -> bool:
        """验证Android包名格式"""
        if not package_name or not isinstance(package_name, str):
            return False
        
        # Android包名格式：com.example.app (允许下划线)
        pattern = r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)*$'
        return bool(re.match(pattern, package_name))
    
    @staticmethod
    def validate_file_path(file_path: str) -> bool:
        """验证文件路径是否存在且可读"""
        try:
            path = Path(file_path)
            return path.exists() and path.is_file()
        except Exception:
            return False
    
    @staticmethod
    def validate_directory_path(dir_path: str) -> bool:
        """验证目录路径是否存在"""
        try:
            path = Path(dir_path)
            return path.exists() and path.is_dir()
        except Exception:
            return False
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """清理文件名，移除非法字符"""
        # 移除或替换非法字符
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        sanitized = filename
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')
        
        # 移除首尾空格和点
        sanitized = sanitized.strip(' .')
        
        # 确保不为空
        if not sanitized:
            sanitized = "unnamed"
        
        return sanitized
    
    @staticmethod
    def validate_utg_data(utg_data: Dict[str, Any]) -> List[str]:
        """验证UTG数据格式"""
        errors = []
        
        if not isinstance(utg_data, dict):
            errors.append("UTG data must be a dictionary")
            return errors
        
        # 检查必需字段
        if 'nodes' not in utg_data:
            errors.append("Missing 'nodes' field in UTG data")
        elif not isinstance(utg_data['nodes'], list):
            errors.append("'nodes' must be a list")
        
        if 'edges' not in utg_data:
            errors.append("Missing 'edges' field in UTG data")
        elif not isinstance(utg_data['edges'], list):
            errors.append("'edges' must be a list")
        
        return errors