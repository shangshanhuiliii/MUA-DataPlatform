import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)

class FileUtils:
    """文件操作工具类"""

    DEFAULT_LOCK_TIMEOUT = 30  # 默认锁超时时间（秒）

    @staticmethod
    def _get_lock_path(file_path: Path) -> Path:
        """获取文件锁路径"""
        return file_path.parent / f".{file_path.name}.lock"

    @staticmethod
    def read_json_file(file_path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Optional[Dict[str, Any]]:
        """读取JSON文件

        Args:
            file_path: JSON文件路径
            timeout: 锁超时时间（秒）

        Returns:
            Optional[Dict[str, Any]]: JSON数据字典，失败返回None
        """
        lock_path = FileUtils._get_lock_path(file_path)
        lock = FileLock(lock_path, timeout=timeout, mode=0o666)

        try:
            with lock:
                if not file_path.exists():
                    logger.warning(f"JSON file not found: {file_path}")
                    return None

                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Timeout:
            logger.error(f"Timeout acquiring lock for {file_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading JSON file {file_path}: {e}")
            return None
    
    @staticmethod
    def write_json_file(file_path: Path, data: Dict[str, Any], timeout: float = DEFAULT_LOCK_TIMEOUT) -> bool:
        """写入JSON文件

        Args:
            file_path: JSON文件路径
            data: 要写入的数据字典
            timeout: 锁超时时间（秒）

        Returns:
            bool: 写入是否成功
        """
        lock_path = FileUtils._get_lock_path(file_path)
        lock = FileLock(lock_path, timeout=timeout, mode=0o666)

        try:
            with lock:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Timeout:
            logger.error(f"Timeout acquiring lock for {file_path}")
            return False
        except Exception as e:
            logger.error(f"Error writing JSON file {file_path}: {e}")
            return False
    
    @staticmethod
    def get_directory_size(dir_path: Path) -> int:
        """获取目录大小"""
        try:
            total_size = 0
            for dirpath, _, filenames in os.walk(dir_path):
                for filename in filenames:
                    file_path = Path(dirpath) / filename
                    if file_path.exists():
                        total_size += file_path.stat().st_size
            return total_size
        except Exception as e:
            logger.error(f"Error calculating directory size {dir_path}: {e}")
            return 0
    
    @staticmethod
    def get_file_creation_time(file_path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Optional[datetime]:
        """获取文件创建时间

        Args:
            file_path: 文件路径
            timeout: 锁超时时间（秒）

        Returns:
            Optional[datetime]: 文件创建时间，失败返回None
        """
        lock_path = FileUtils._get_lock_path(file_path)
        lock = FileLock(lock_path, timeout=timeout, mode=0o666)

        try:
            with lock:
                if file_path.exists():
                    timestamp = file_path.stat().st_ctime
                    return datetime.fromtimestamp(timestamp)
                return None
        except Timeout:
            logger.error(f"Timeout acquiring lock for {file_path}")
            return None
        except Exception as e:
            logger.error(f"Error getting creation time for {file_path}: {e}")
            return None
    
    @staticmethod
    def get_file_modification_time(file_path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Optional[datetime]:
        """获取文件修改时间

        Args:
            file_path: 文件路径
            timeout: 锁超时时间（秒）

        Returns:
            Optional[datetime]: 文件修改时间，失败返回None
        """
        lock_path = FileUtils._get_lock_path(file_path)
        lock = FileLock(lock_path, timeout=timeout, mode=0o666)

        try:
            with lock:
                if file_path.exists():
                    timestamp = file_path.stat().st_mtime
                    return datetime.fromtimestamp(timestamp)
                return None
        except Timeout:
            logger.error(f"Timeout acquiring lock for {file_path}")
            return None
        except Exception as e:
            logger.error(f"Error getting modification time for {file_path}: {e}")
            return None
    
    @staticmethod
    def list_subdirectories(dir_path: Path) -> List[str]:
        """列出目录下的所有子目录"""
        try:
            if not dir_path.exists() or not dir_path.is_dir():
                return []
            
            subdirs = []
            for item in dir_path.iterdir():
                if item.is_dir():
                    subdirs.append(item.name)
            return sorted(subdirs)
        except Exception as e:
            logger.error(f"Error listing subdirectories in {dir_path}: {e}")
            return []
    
    @staticmethod
    def count_files_in_directory(dir_path: Path, pattern: str = "*") -> int:
        """统计目录中指定模式的文件数量"""
        try:
            if not dir_path.exists() or not dir_path.is_dir():
                return 0
            
            return len(list(dir_path.glob(pattern)))
        except Exception as e:
            logger.error(f"Error counting files in {dir_path}: {e}")
            return 0
    
    @staticmethod
    def ensure_directory_exists(dir_path: Path) -> bool:
        """确保目录存在，不存在则创建"""
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Error creating directory {dir_path}: {e}")
            return False
    
    @staticmethod
    def safe_remove_file(file_path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT) -> bool:
        """安全删除文件

        Args:
            file_path: 要删除的文件路径
            timeout: 锁超时时间（秒）

        Returns:
            bool: 删除是否成功
        """
        lock_path = FileUtils._get_lock_path(file_path)
        lock = FileLock(lock_path, timeout=timeout, mode=0o666)

        try:
            with lock:
                if file_path.exists():
                    file_path.unlink()
            return True
        except Timeout:
            logger.error(f"Timeout acquiring lock for {file_path}")
            return False
        except Exception as e:
            logger.error(f"Error removing file {file_path}: {e}")
            return False
    
    @staticmethod
    def backup_file(file_path: Path, backup_suffix: str = ".backup", timeout: float = DEFAULT_LOCK_TIMEOUT) -> bool:
        """备份文件

        Args:
            file_path: 要备份的文件路径
            backup_suffix: 备份文件后缀
            timeout: 锁超时时间（秒）

        Returns:
            bool: 备份是否成功
        """
        lock_path = FileUtils._get_lock_path(file_path)
        lock = FileLock(lock_path, timeout=timeout, mode=0o666)

        try:
            with lock:
                if not file_path.exists():
                    return False

                backup_path = file_path.with_suffix(file_path.suffix + backup_suffix)
                shutil.copy2(file_path, backup_path)
            return True
        except Timeout:
            logger.error(f"Timeout acquiring lock for {file_path}")
            return False
        except Exception as e:
            logger.error(f"Error backing up file {file_path}: {e}")
            return False

    @staticmethod
    def read_yaml_file(file_path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Optional[Dict[str, Any]]:
        """读取YAML文件

        Args:
            file_path: YAML文件路径
            timeout: 锁超时时间（秒）

        Returns:
            Optional[Dict[str, Any]]: YAML数据字典，失败返回None
        """
        lock_path = FileUtils._get_lock_path(file_path)
        lock = FileLock(lock_path, timeout=timeout, mode=0o666)

        try:
            with lock:
                if not file_path.exists():
                    logger.warning(f"YAML file not found: {file_path}")
                    return None

                with open(file_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
        except Timeout:
            logger.error(f"Timeout acquiring lock for {file_path}")
            return None
        except yaml.YAMLError as e:
            logger.error(f"YAML parse error in {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading YAML file {file_path}: {e}")
            return None

    @staticmethod
    def write_yaml_file(file_path: Path, data: Dict[str, Any], timeout: float = DEFAULT_LOCK_TIMEOUT) -> bool:
        """写入YAML文件（从字典生成）

        Args:
            file_path: YAML文件路径
            data: 要写入的数据字典
            timeout: 锁超时时间（秒）

        Returns:
            bool: 写入是否成功
        """
        lock_path = FileUtils._get_lock_path(file_path)
        lock = FileLock(lock_path, timeout=timeout, mode=0o666)

        try:
            with lock:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return True
        except Timeout:
            logger.error(f"Timeout acquiring lock for {file_path}")
            return False
        except Exception as e:
            logger.error(f"Error writing YAML file {file_path}: {e}")
            return False

    @staticmethod
    def read_file(file_path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Optional[str]:
        """读取文件内容

        Args:
            file_path: 文件路径
            timeout: 锁超时时间（秒）

        Returns:
            Optional[str]: 文件内容字符串，如果文件不存在或读取失败返回None
        """
        lock_path = FileUtils._get_lock_path(file_path)
        lock = FileLock(lock_path, timeout=timeout, mode=0o666)

        try:
            with lock:
                if not file_path.exists():
                    logger.warning(f"File not found: {file_path}")
                    return None

                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Timeout:
            logger.error(f"Timeout acquiring lock for {file_path}")
            return None
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return None

    @staticmethod
    def write_file(file_path: Path, content: str, timeout: float = DEFAULT_LOCK_TIMEOUT) -> bool:
        """写入文件

        Args:
            file_path: 文件路径
            content: 文件内容字符串
            timeout: 锁超时时间（秒）

        Returns:
            bool: 写入是否成功
        """
        lock_path = FileUtils._get_lock_path(file_path)
        lock = FileLock(lock_path, timeout=timeout, mode=0o666)

        try:
            with lock:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            return True
        except Timeout:
            logger.error(f"Timeout acquiring lock for {file_path}")
            return False
        except Exception as e:
            logger.error(f"Error writing file to {file_path}: {e}")
            return False
    