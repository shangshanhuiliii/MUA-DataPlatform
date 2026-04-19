"""
Task Info YAML management service

负责在每个录制目录下管理 task-info.yaml 文件
"""
from collections import defaultdict
import logging
from pathlib import Path
from string import Template
from typing import Optional

from ..config import Config
from ..utils.file_utils import FileUtils

logger = logging.getLogger(__name__)


class TaskService:
    """Task Info 服务类

    负责在每个录制目录下管理 task-info.yaml 文件的创建、读取、更新和删除
    """

    # Task info YAML filename
    TASK_INFO_YAML = "task-info.yaml"

    # Task info template file path
    TASK_INFO_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "task-info-template.yaml"

    @staticmethod
    def _load_task_info_template() -> str:
        """加载 task-info.yaml 模板文件内容

        Returns:
            str: 模板文件内容

        Raises:
            FileNotFoundError: 如果模板文件不存在
            IOError: 如果读取模板文件失败
        """
        if not TaskService.TASK_INFO_TEMPLATE_PATH.exists():
            raise FileNotFoundError(
                f"Template file not found: {TaskService.TASK_INFO_TEMPLATE_PATH}"
            )

        try:
            with open(TaskService.TASK_INFO_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading template file: {e}")
            raise IOError(f"Failed to load template file: {e}") from e

    # ========== Recording级别的Task Info YAML管理 ==========

    @staticmethod
    def _recording_exists(recording_name: str) -> bool:
        """检查录制目录是否存在"""
        if not recording_name:
            return False
        data_path = Config.DATA_DIR / recording_name
        return data_path.exists() and (data_path / "utg.json").exists()

    @staticmethod
    def _get_recording_path(recording_name: str) -> Path:
        """获取录制目录的绝对路径"""
        if not TaskService._recording_exists(recording_name):
            raise ValueError(f"Recording '{recording_name}' does not exist")
        return Config.DATA_DIR / recording_name

    @staticmethod
    def _get_task_info_path(recording_name: str) -> Path:
        """获取指定录制目录的task-info.yaml文件路径"""
        return TaskService._get_recording_path(recording_name) / TaskService.TASK_INFO_YAML

    @staticmethod
    def get_task_info(recording_name: str) -> Optional[str]:
        """获取指定录制目录的task-info

        Args:
            recording_name: 录制目录名称 (如 "record/task_xxx" 或 "exploration/xxx")

        Returns:
            Optional[str]: 任务信息的YAML格式字符串，如果不存在返回None
        """
        task_info_path = TaskService._get_task_info_path(recording_name)
        if not task_info_path.exists():
            # task-info.yaml 不存在，创建空的 task-info
            logger.info(f"Task info not found in recording '{recording_name}', creating empty task-info from template")
            try:
                return TaskService.create_task_info(recording_name, task_id="", description="")
            except Exception as e:
                logger.error(f"Failed to create empty task-info for recording '{recording_name}': {e}")
                return None

        return FileUtils.read_file(task_info_path)

    @staticmethod
    def create_task_info(recording_name: str, task_id: str, description: Optional[str] = None,
                        **kwargs) -> str:
        """在指定录制目录中创建task-info.yaml

        使用 string.Template 和模板文件生成 YAML 内容

        Args:
            recording_name: 录制目录名称
            task_id: 任务ID (数据库中的任务ID)
            description: 任务描述 (可选，如果未提供则从数据库中获取)
            **kwargs: 其他模板变量，例如 background, expected_actions 等

        Returns:
            str: 创建的任务信息的YAML格式字符串

        Raises:
            FileExistsError: 如果task-info.yaml已存在
            ValueError: 如果录制目录不存在
        """
        # 验证录制目录是否存在
        TaskService._get_recording_path(recording_name)

        task_info_path = TaskService._get_task_info_path(recording_name)
        if task_info_path.exists():
            raise FileExistsError(f"Task info already exists in recording '{recording_name}'")

        # 如果未提供 description，从数据库中获取
        if description is None and task_id:
            try:
                from backend.database import engine
                from backend.models.task import Task
                from sqlmodel import Session
                with Session(engine) as session:
                    db_task = session.get(Task, int(task_id))
                    if db_task:
                        description = db_task.description
                        logger.info(f"Retrieved description from database for task_id '{task_id}': {description}")
                    else:
                        logger.warning(f"Task with id '{task_id}' not found in database")
                        description = ""
            except Exception as e:
                logger.warning(f"Failed to get task description from database: {e}")
                description = ""

        if description is None:
            description = ""

        # 加载模板并使用 string.Template 替换变量
        template_content = TaskService._load_task_info_template()
        template = Template(template_content)

        # 准备模板变量：合并固定参数和 kwargs, 使用 defaultdict 将未指定值设置为空
        template_vars = defaultdict(str, {"id": task_id, "description": description, **kwargs})

        yaml_content = template.substitute(template_vars)

        # 使用 FileUtils 写入文件
        if not FileUtils.write_file(task_info_path, yaml_content):
            raise IOError(f"Failed to create task-info.yaml in recording '{recording_name}'")

        logger.info(f"Created task-info.yaml in recording '{recording_name}'")
        return yaml_content

    @staticmethod
    def update_task_info(recording_name: str, task_info_yaml: str) -> str:
        """更新指定录制目录的task-info.yaml

        解析传入的 YAML 字符串，使用模板进行变量替换后保存

        Args:
            recording_name: 录制目录名称
            task_info_yaml: 任务信息的YAML格式字符串

        Returns:
            str: 更新后的任务信息的YAML格式字符串

        Raises:
            FileNotFoundError: 如果task-info.yaml不存在
            ValueError: 如果YAML格式无效或缺少必需字段
        """
        task_info_path = TaskService._get_task_info_path(recording_name)
        if not task_info_path.exists():
            raise FileNotFoundError(f"Task info not found in recording '{recording_name}'")

        # 解析 YAML 字符串
        import yaml
        try:
            task_data = yaml.safe_load(task_info_yaml)
            if not isinstance(task_data, dict):
                raise ValueError("YAML content must be a dictionary")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format: {e}")

        # 加载模板并使用 string.Template 替换变量
        template_content = TaskService._load_task_info_template()
        template = Template(template_content)

        # 使用 task_data 进行模板替换
        try:
            # 处理加载出的文本利用模板保存时不会自动换行的问题
            for key, value in task_data.items():
                if isinstance(value, str) and "\n" in value:
                    task_data[key] = "\n  ".join(value.split("\n"))
            template_vars = defaultdict(str, task_data)
            yaml_content = template.substitute(template_vars)
        except KeyError as e:
            raise ValueError(f"Missing required field in task_info_yaml: {e}")

        # 使用 FileUtils 写入文件
        if not FileUtils.write_file(task_info_path, yaml_content):
            raise IOError(f"Failed to update task-info.yaml in recording '{recording_name}'")

        logger.info(f"Updated task-info.yaml in recording '{recording_name}'")
        return yaml_content

    @staticmethod
    def delete_task_info(recording_name: str) -> bool:
        """删除指定录制目录的task-info.yaml

        Args:
            recording_name: 录制目录名称

        Returns:
            bool: 删除是否成功
        """
        task_info_path = TaskService._get_task_info_path(recording_name)
        if not task_info_path.exists():
            logger.warning(f"Task info not found in recording '{recording_name}'")
            return False

        success = FileUtils.safe_remove_file(task_info_path)
        if success:
            logger.info(f"Deleted task-info.yaml from recording '{recording_name}'")
        return success
