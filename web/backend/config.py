import os
import json
import logging
from pathlib import Path

class Config:
    # 日志级别配置
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def get_log_level(cls) -> int:
        """获取日志级别的数值"""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(cls.LOG_LEVEL, logging.INFO)

    # 数据目录配置
    DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
    # RECORD_DIR 可以通过环境变量覆盖，但必须位于 DATA_DIR 下
    RECORD_DIR = Path(os.getenv("RECORD_DIR", str(DATA_DIR / "record")))

    # API 配置
    CORS_ORIGINS = json.loads(os.getenv("CORS_ORIGINS", '["*"]'))

    # 服务器配置
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8888"))
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"

    # 有效的事件类型
    VALID_EVENT_TYPES = [
        # 简化名称（保持向后兼容）
        "touch", "hotkey", "intent", "set_text", "put_text",
        "long_touch", "swipe", "scroll", "manual",
        # 完整类名（用于UTG事件字符串）
        "TouchEvent", "KeyEvent", "IntentEvent", "SetTextEvent", "PutTextEvent",
        "LongTouchEvent", "SwipeEvent", "ScrollEvent", "ManualEvent"
    ]

    # 文件路径配置
    STATIC_DIR = Path("static")
    TEMPLATES_DIR = Path("templates")
    STYLESHEETS_DIR = Path("stylesheets")  # 为了向后兼容

    @classmethod
    def validate_paths(cls) -> None:
        """校验路径配置，避免 directory_name 语义分叉。"""
        data_dir = cls.DATA_DIR.resolve()
        record_dir = cls.RECORD_DIR.resolve()

        try:
            relative_path = record_dir.relative_to(data_dir)
        except ValueError as exc:
            raise ValueError(
                f"Invalid path config: RECORD_DIR ({cls.RECORD_DIR}) must be a subdirectory of DATA_DIR ({cls.DATA_DIR})"
            ) from exc

        if relative_path == Path("."):
            raise ValueError(
                f"Invalid path config: RECORD_DIR ({cls.RECORD_DIR}) must be a subdirectory of DATA_DIR ({cls.DATA_DIR})"
            )

    @classmethod
    def validate_event_type(cls, event_type: str) -> bool:
        """验证事件类型是否有效"""
        return event_type in cls.VALID_EVENT_TYPES

    # YOLO管理器相关配置
    YOLO_MAX_QUEUE_SIZE = int(os.getenv("YOLO_MAX_QUEUE_SIZE", "64"))
    YOLO_NUM_THREADS = int(os.getenv("YOLO_NUM_THREADS", "1"))
    YOLO_INFERENCE_TIMEOUT = int(os.getenv("YOLO_INFERENCE_TIMEOUT", "30"))
    YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", None)
    YOLO_ONNX_IMGSZ = int(os.getenv("YOLO_ONNX_IMGSZ", "640"))
    YOLO_ONNX_CONF = float(os.getenv("YOLO_ONNX_CONF", "0.2"))
    YOLO_ONNX_IOU = float(os.getenv("YOLO_ONNX_IOU", "0.7"))

    @classmethod
    def get_yolo_config(cls):
        return {
            "max_queue_size": cls.YOLO_MAX_QUEUE_SIZE,
            "num_threads": cls.YOLO_NUM_THREADS,
            "inference_timeout": cls.YOLO_INFERENCE_TIMEOUT,
            "yolo_model_path": cls.YOLO_MODEL_PATH,
            "onnx_imgsz": cls.YOLO_ONNX_IMGSZ,
            "onnx_conf": cls.YOLO_ONNX_CONF,
            "onnx_iou": cls.YOLO_ONNX_IOU,
        }