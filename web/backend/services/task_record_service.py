"""
TaskRecordService - Thread+Queue录制服务
基于线程和队列的轻量级录制服务实现
提供WebSocket接口进行设备屏幕流和录制会话管理
"""

import asyncio
import base64
import logging
import os
import queue
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set
from droidbot.constant import ViewsMode

from fastapi import WebSocket, WebSocketDisconnect

from backend.auth.security import decode_token_with_status
from backend.errors import AppError, app_error
from .recording_worker_thread import RecordingWorkerThread
from backend.session_config import (
    DEVICE_SESSION_IDLE_TIMEOUT_SECONDS,
    RECORDING_RUNTIME_LEASE_SECONDS,
    WEBSOCKET_PING_INTERVAL,
    WEBSOCKET_PONG_TIMEOUT,
    workspace_state_manager,
)


MAX_RECORDING_DESCRIPTION_BYTES = 80
STOP_REASON_USER = "user_stop"
STOP_REASON_DISCONNECT = "disconnect"
STOP_REASON_TIMEOUT = "timeout"
STOP_REASON_AUTH_EXPIRED = "auth_expired"
STOP_REASON_EXPIRED_CLEANUP = "expired_cleanup"


def update_task_status(task_id: int, status: str):
    """更新任务状态（在独立数据库会话中执行）"""
    from backend.database import engine
    from backend.models.task import Task
    from sqlmodel import Session

    try:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if task:
                task.status = status
                session.add(task)
                session.commit()
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to update task status: {e}")


def resolve_recording_creator_from_token(auth_token: str) -> dict:
    """根据 JWT 解析当前录制用户"""
    from sqlmodel import Session, select

    from ..database import engine
    from ..models.user import User

    payload, token_status = decode_token_with_status(auth_token, expected_type="access")
    if token_status == "expired":
        raise ValueError("Access token expired")
    if payload is None:
        raise ValueError("Invalid auth token")

    username = payload.get("sub")
    if not username:
        raise ValueError("Invalid auth token")

    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            raise ValueError("Could not resolve auth token user")
        if not user.is_active:
            raise ValueError("Inactive user")
        return {
            "id": user.id,
            "username": user.username,
            "is_superuser": user.is_superuser,
        }


def resolve_recording_creator_from_user_id(user_id: int) -> dict:
    """根据用户 ID 解析录制用户信息"""
    from sqlmodel import Session, select

    from ..database import engine
    from ..models.user import User

    with Session(engine) as session:
        user = session.exec(select(User).where(User.id == user_id)).first()
        if user is None:
            raise ValueError("Could not resolve device session user")
        if not user.is_active:
            raise ValueError("Inactive user")
        return {
            "id": user.id,
            "username": user.username,
            "is_superuser": user.is_superuser,
        }


def validate_recording_creator_access(task_id: int, creator: dict):
    """校验录制用户是否有权录制该任务"""
    from sqlmodel import Session

    from ..database import engine
    from ..crud import task as task_crud

    with Session(engine) as session:
        task = task_crud.get_task_by_id(session, task_id)
        if not task:
            raise ValueError("Task not found")

        if not creator["is_superuser"]:
            has_access = task_crud.is_task_assigned_to_user(session, task_id, creator["id"])
            if not has_access:
                raise ValueError("You don't have access to this task")


def ensure_recording_metadata(task_id: int, directory_name: str, recorded_by: int):
    """在独立会话中确保 recording 元数据存在"""
    from sqlmodel import Session

    from ..database import engine
    from ..crud import recording as recording_crud

    with Session(engine) as session:
        recording_crud.ensure_recording(
            session,
            task_id=task_id,
            directory_name=directory_name,
            recorded_by=recorded_by
        )



class RecordingSession:
    """基于Thread+Queue的录制会话 """
    
    def __init__(self, device_serial: str, output_dir: str, dataset: str, user_task_id: str = None, views_mode: ViewsMode = ViewsMode.XML_MODE, use_image_state: bool = False, recording_mode: str = "new_task", service_manager: 'TaskRecordService' = None, creator_user_id: Optional[int] = None):
        self.device_serial = device_serial
        self.output_dir = str(output_dir)
        self.dataset = dataset
        self.user_task_id = user_task_id
        self.views_mode = views_mode
        self.use_image_state = use_image_state
        self.recording_mode = recording_mode
        self.creator_user_id = creator_user_id
        self.session_id = str(uuid.uuid4())
        self.created_time = time.time()
        self.logger = logging.getLogger(f"{__name__}.{device_serial}")
        self.service_manager = service_manager

        # 创建通信队列
        self.event_queue = queue.Queue()
        self.response_queue = queue.Queue()

        # Response monitoring
        self.response_monitor_task = None
        self.monitoring_enabled = False

        # 创建录制线程
        self.recording_thread = RecordingWorkerThread(
            device_serial=self.device_serial,
            output_dir=self.output_dir,
            views_mode=self.views_mode,
            event_queue=self.event_queue,
            response_queue=self.response_queue,
            dataset=self.dataset,
            use_image_state=self.use_image_state,
            recording_mode=self.recording_mode,
            task_id=self.user_task_id  # 传递 task_id 用于创建 task-info.yaml
        )
        
    def start(self) -> bool:
        """启动录制线程"""
        try:
            if self.recording_thread:
                self.recording_thread.start()
                
                # Start response monitoring if service manager is available
                if self.service_manager:
                    self.monitoring_enabled = True
                    self.response_monitor_task = asyncio.create_task(self._monitor_responses())
                
                self.logger.info(f"Recording session started: {self.session_id}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to start recording session: {e}")
            return False
        
    async def stop(self, *, reason: str = STOP_REASON_USER) -> int:
        """停止录制，返回操作计数"""
        try:
            t_start = time.time()

            # Stop response monitoring
            self.logger.debug("Stopping response monitoring...")
            self.monitoring_enabled = False
            if self.response_monitor_task:
                self.response_monitor_task.cancel()
                try:
                    await self.response_monitor_task
                except asyncio.CancelledError:
                    pass
            t_monitor = time.time()
            self.logger.info(f"⏱️ Stop response monitoring took {t_monitor - t_start:.2f}s")

            # 发送关闭信号
            self.logger.debug("Sending shutdown signal to recording thread...")
            if self.event_queue:
                self.event_queue.put({"type": "shutdown"})

            # 等待线程完成
            self.logger.debug("Waiting for recording thread to finish...")
            if self.recording_thread and self.recording_thread.is_alive():
                await asyncio.to_thread(self.recording_thread.join, timeout=10.0)
            t_thread = time.time()
            self.logger.info(f"⏱️ Wait for recording thread took {t_thread - t_monitor:.2f}s")

            # 获取事件计数
            event_count = getattr(self.recording_thread, 'event_count', 0)

            t_total = time.time() - t_start
            self.logger.info(f"Recording session stopped: {self.session_id}, events: {event_count} (total: {t_total:.2f}s)")
            return event_count
            
        except Exception as e:
            self.logger.error(f"Failed to stop recording session: {e}")
            return getattr(self.recording_thread, 'event_count', 0)
        
    async def record_action(self, action: dict):
        """记录用户操作到队列"""
        if self.recording_thread and self.recording_thread.is_alive():
            timestamped_event = {
                **action,
                'timestamp': time.time(),
                'session_id': self.session_id
            }
            self.event_queue.put(timestamped_event)
            self.logger.debug(f"Action queued: {action.get('type', 'unknown')}")

    async def pause(self):
        """暂停录制，后续操作继续执行但不记录"""
        if self.recording_thread and self.recording_thread.is_alive():
            self.event_queue.put({
                "type": "pause_recording",
                "timestamp": time.time(),
                "session_id": self.session_id
            })
            self.logger.debug("Pause command queued")

    async def resume(self):
        """恢复录制"""
        if self.recording_thread and self.recording_thread.is_alive():
            self.event_queue.put({
                "type": "resume_recording",
                "timestamp": time.time(),
                "session_id": self.session_id
            })
            self.logger.debug("Resume command queued")
            
    def is_alive(self) -> bool:
        """检查录制线程是否活跃"""
        return self.recording_thread and self.recording_thread.is_alive()
    
    async def _monitor_responses(self):
        """监控响应队列并转发操作反馈到WebSocket客户端"""
        self.logger.info(f"Started response monitoring for session {self.session_id}")
        
        while self.monitoring_enabled:
            try:
                # 使用 asyncio.to_thread 将阻塞的队列操作转为异步
                try:
                    response = await asyncio.to_thread(
                        self.response_queue.get, 
                        timeout=0.5  # 500ms timeout to allow regular monitoring checks
                    )
                    
                    await self._process_response(response)
                    
                except queue.Empty:
                    # Timeout is expected, continue monitoring
                    continue
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in response monitoring: {e}")
                await asyncio.sleep(0.1)  # Brief pause on error
                
        self.logger.info(f"Stopped response monitoring for session {self.session_id}")
    
    async def _process_response(self, response: dict):
        """处理从录制线程收到的响应并转发到前端"""
        try:
            response_type = response.get("type")
            
            if response_type == "recording_ready":
                await self._forward_recording_ready(response, success=True)
                self.logger.info(f"Recording thread ready for session {self.session_id}")
            elif response_type == "recording_paused":
                await self._forward_recording_state(response, "recording_paused")
            elif response_type == "recording_resumed":
                await self._forward_recording_state(response, "recording_resumed")
            elif response_type == "event_completed":
                # 将操作完成信号转换为前端期望的格式
                await self._forward_operation_feedback(response, success=True)
            elif response_type == "event_error":
                # 处理操作失败
                await self._forward_operation_feedback(response, success=False)
            elif response_type == "error":
                # 处理一般错误
                await self._forward_operation_feedback(response, success=False)
            else:
                self.logger.debug(f"Received response: {response}")
                
        except Exception as e:
            self.logger.error(f"Error processing response: {e}")

    async def _forward_recording_ready(self, response: dict, success: bool):
        """将录制准备完成转发给WebSocket客户端"""
        try:
            if not self.service_manager:
                return

            if success and self.recording_mode == "new_task" and self.user_task_id and self.creator_user_id:
                try:
                    await self.service_manager._ensure_recording_entry(
                        task_id=int(self.user_task_id),
                        directory_name=self.dataset,
                        recorded_by=self.creator_user_id
                    )
                except Exception as e:
                    self.logger.error(f"Failed to persist recording metadata for {self.dataset}: {e}")
                    await self.service_manager.broadcast_to_device_clients(
                        self.device_serial,
                        {
                            "type": "recording_error",
                            "device_serial": self.device_serial,
                            "message": f"Failed to persist recording metadata: {str(e)}",
                            "timestamp": response.get("timestamp", time.time())
                        }
                    )
                    await self._abort_recording_startup()
                    return

            if success:
                try:
                    await workspace_state_manager.set_runtime_state(self.session_id, "recording")
                except AppError as exc:
                    await self.service_manager.broadcast_to_device_clients(
                        self.device_serial,
                        {
                            "type": "session_event",
                            "scope": "runtime",
                            "code": exc.code,
                            "message": exc.detail,
                            "timestamp": response.get("timestamp", time.time()),
                        }
                    )
                    await self._abort_recording_startup()
                    return

            # 构造操作反馈消息
            feedback_message = {
                "type": "recording_ready",
                "device_serial": self.device_serial,
                "session_id": self.session_id,
                "dataset": self.dataset,
                "task_id": self.user_task_id,  # 添加 task_id 用于创建 Recording 记录
                "recording_mode": self.recording_mode,
                "success": success,
                "architecture": "threaded_independent",
                "timestamp": response.get("timestamp", time.time())
            }
            
            # 通过service manager广播到设备客户端
            await self.service_manager.broadcast_to_device_clients(
                self.device_serial, 
                feedback_message
            )

        except Exception as e:
            self.logger.error(f"Error recording ready feedback: {e}")

    async def _abort_recording_startup(self):
        """启动阶段失败时清理会话，避免线程继续运行却表现为启动成功。"""
        try:
            self.monitoring_enabled = False

            if self.event_queue:
                self.event_queue.put({"type": "shutdown"})

            if self.recording_thread and self.recording_thread.is_alive():
                await asyncio.to_thread(self.recording_thread.join, timeout=10.0)

            if self.user_task_id and self.recording_mode == "new_task":
                try:
                    update_task_status(int(self.user_task_id), "pending")
                except Exception as e:
                    self.logger.warning(f"Failed to revert task status after startup abort: {e}")

            try:
                await workspace_state_manager.release_runtime_session(self.session_id, status="failed")
            except AppError:
                pass

            if self.service_manager:
                async with self.service_manager.recording_sessions_lock:
                    self.service_manager.recording_sessions.pop(self.session_id, None)
        except Exception as e:
            self.logger.error(f"Failed to abort recording startup for {self.session_id}: {e}")

    async def _forward_recording_state(self, response: dict, response_type: str):
        """转发录制状态变化（暂停/恢复）"""
        try:
            if not self.service_manager:
                return

            feedback_message = {
                "type": response_type,
                "device_serial": self.device_serial,
                "session_id": self.session_id,
                "dataset": self.dataset,
                "event_count": response.get("event_count", 0),
                "timestamp": response.get("timestamp", time.time())
            }

            await self.service_manager.broadcast_to_device_clients(
                self.device_serial,
                feedback_message
            )
            state = "paused" if response_type == "recording_paused" else "recording"
            await workspace_state_manager.set_runtime_state(self.session_id, state)
        except Exception as e:
            self.logger.error(f"Error forwarding recording state feedback: {e}")
    
    async def _forward_operation_feedback(self, response: dict, success: bool):
        """将操作反馈转发给WebSocket客户端"""
        try:
            if not self.service_manager:
                return
                
            # 构造操作反馈消息
            feedback_message = {
                "type": "operation_feedback",
                "device_serial": self.device_serial,
                "session_id": self.session_id,
                "dataset": self.dataset,
                "success": success,
                "recorded": response.get("recorded", True),
                "recording_state": response.get("recording_state", "recording"),
                "timestamp": response.get("timestamp", time.time())
            }
            
            # 添加操作类型和数据
            if response.get("operation_type"):
                feedback_message["operation_type"] = response.get("operation_type")
                
            if response.get("operation_data"):
                feedback_message["data"] = response.get("operation_data")
            
            # 添加具体的反馈信息
            if success:
                feedback_message["event_count"] = response.get("event_count", 0)
                feedback_message["message"] = "Operation completed successfully"
            else:
                # 处理错误信息，支持多种错误类型
                error_msg = response.get("error_message") or response.get("message", "Unknown error")
                feedback_message["error_message"] = error_msg
                feedback_message["message"] = "Operation failed"
            
            # 通过service manager广播到设备客户端
            await self.service_manager.broadcast_to_device_clients(
                self.device_serial, 
                feedback_message
            )
            
            self.logger.debug(f"Forwarded operation feedback: {response.get('operation_type', 'unknown')} success={success}")
            
        except Exception as e:
            self.logger.error(f"Error forwarding operation feedback: {e}")
    
    def get_session_info(self) -> dict:
        """获取会话信息"""
        return {
            'session_id': self.session_id,
            'device_serial': self.device_serial,
            'user_task_id': self.user_task_id,
            'output_dir': self.output_dir,
            'views_mode': self.views_mode,
            'use_image_state': self.use_image_state,
            'creator_user_id': self.creator_user_id,
            'created_time': self.created_time,
            'is_alive': self.is_alive(),
            'event_count': getattr(self.recording_thread, 'event_count', 0),
            'is_paused': getattr(self.recording_thread, 'is_paused', False)
        }


class DeviceScreenStream:
    """
    单个设备的屏幕流处理（集成到TaskRecordService中）
    负责屏幕流的捕获和广播
    """
    
    def __init__(self, device_serial: str, manager: 'TaskRecordService'):
        self.device_serial = device_serial
        self.manager = manager
        self.logger = logging.getLogger(f"{__name__}.{device_serial}")
        self.pyscrcpy_client = None
        self.running = False
        self.stream_thread = None
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.message_queue = queue.Queue()
        self.broadcast_task = None
    
    async def start(self):
        """启动设备屏幕流"""
        try:
            # 设置 pyscrcpy
            if not await self._try_setup_pyscrcpy():
                raise Exception("Failed to initialize pyscrcpy - task record only supports pyscrcpy")
            
            self.logger.info(f"Using pyscrcpy for device {self.device_serial}")
            
            # 启动屏幕流线程
            self.running = True
            self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
            self.stream_thread.start()
            
            # 启动消息广播任务
            self.broadcast_task = asyncio.create_task(self._broadcast_loop())
            
            self.logger.info(f"Device stream started for {self.device_serial}")
            
        except Exception as e:
            self.logger.error(f"Failed to start device stream: {e}")
            raise
    
    async def stop(self):
        """停止设备屏幕流"""
        t_start = time.time()
        self.logger.info(f"Stopping device stream for {self.device_serial}...")

        self.running = False

        # 停止流线程
        self.logger.debug("Stopping stream thread...")
        if self.stream_thread and self.stream_thread.is_alive():
            await asyncio.to_thread(self.stream_thread.join, timeout=5)
        t_stream = time.time()
        self.logger.info(f"⏱️ Stop stream thread took {t_stream - t_start:.2f}s")

        # 停止广播任务
        self.logger.debug("Stopping broadcast task...")
        if self.broadcast_task:
            self.broadcast_task.cancel()
            try:
                await self.broadcast_task
            except asyncio.CancelledError:
                pass
        t_broadcast = time.time()
        self.logger.info(f"⏱️ Stop broadcast task took {t_broadcast - t_stream:.2f}s")

        # 停止 pyscrcpy 客户端
        self.logger.debug("Stopping pyscrcpy client...")
        if self.pyscrcpy_client:
            try:
                await asyncio.to_thread(self.pyscrcpy_client.stop)
                self.pyscrcpy_client = None
            except Exception as e:
                self.logger.error(f"Error stopping pyscrcpy client: {e}")
        t_pyscrcpy = time.time()
        self.logger.info(f"⏱️ Stop pyscrcpy client took {t_pyscrcpy - t_broadcast:.2f}s")

        t_total = time.time() - t_start
        self.logger.info(f"Device stream stopped for {self.device_serial} (total: {t_total:.2f}s)")
    
    async def _try_setup_pyscrcpy(self):
        """尝试设置 pyscrcpy 客户端"""
        try:
            from pyscrcpy import Client
            
            # 创建 pyscrcpy 客户端
            self.pyscrcpy_client = Client(
                device=self.device_serial,
                max_fps=20,
                max_size=1080,
                bitrate=8000000  # 8Mbps
            )
            
            # 设置帧回调
            self.pyscrcpy_client.on_frame(self._on_pyscrcpy_frame)
            
            # 启动客户端（异步模式）
            await asyncio.to_thread(self.pyscrcpy_client.start, threaded=True)
            
            # 等待连接建立
            await asyncio.sleep(2)
            
            if self.pyscrcpy_client.last_frame is not None:
                return True
            else:
                self.logger.warning("pyscrcpy failed to capture initial frame")
                return False
                
        except ImportError:
            self.logger.warning("pyscrcpy not available")
            return False
        except Exception as e:
            self.logger.error(f"Failed to setup pyscrcpy: {e}")
            if self.pyscrcpy_client:
                try:
                    self.pyscrcpy_client.stop()
                except:
                    pass
                self.pyscrcpy_client = None
            return False
    
    def _on_pyscrcpy_frame(self, client, frame):
        """pyscrcpy 帧回调函数"""
        _ = client  # 明确标记为未使用
        with self.frame_lock:
            self.latest_frame = frame.copy()
    
    async def _broadcast_loop(self):
        """异步消息广播循环"""
        while self.running:
            try:
                # 从队列中获取消息（非阻塞）
                try:
                    message = self.message_queue.get_nowait()
                    await self.manager.broadcast_to_device_clients(self.device_serial, message)
                    self.message_queue.task_done()
                except queue.Empty:
                    await asyncio.sleep(0.01)  # 10ms休息
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in broadcast loop: {e}")
                await asyncio.sleep(0.1)
    
    def _stream_loop(self):
        """屏幕流循环（在单独线程中运行）- 使用 pyscrcpy"""
        while self.running:
            try:
                # 使用 pyscrcpy 获取屏幕帧
                with self.frame_lock:
                    if self.latest_frame is not None:
                        frame = self.latest_frame.copy()
                    else:
                        frame = None
                
                if frame is not None:
                    timestamp = datetime.now().isoformat()
                    
                    # 将 OpenCV 帧编码为 JPEG
                    import cv2
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    image_base64 = base64.b64encode(buffer).decode('utf-8')
                    
                    # 获取帧尺寸
                    height, width = frame.shape[:2]
                    
                    # 创建消息
                    message = {
                        "type": "screen_frame",
                        "device_serial": self.device_serial,
                        "timestamp": timestamp,
                        "image": f"data:image/jpeg;base64,{image_base64}",
                        "width": width,
                        "height": height,
                        "orientation": 0  # pyscrcpy 通常返回正常方向
                    }
                    
                    # 将消息放入队列等待广播
                    self.message_queue.put(message)
                
                # 20 FPS for pyscrcpy
                time.sleep(0.05)
                
            except Exception as e:
                self.logger.error(f"Error in stream loop: {e}")
                time.sleep(1)


class TaskRecordService:
    """独立完整的任务录制服务 - 集成屏幕流管理、设备连接、WebSocket通信和录制会话管理"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # WebSocket连接管理
        self.connections: Dict[str, Set[WebSocket]] = {}  # device_serial -> set of websockets
        self.connection_clients: Dict[int, dict] = {}  # websocket_id -> connection_info
        
        # 设备和屏幕流管理
        self.device_streams: Dict[str, DeviceScreenStream] = {}  # device_serial -> stream instance
        self.active_devices: Set[str] = set()
        
        # 录制会话管理
        self.recording_sessions: Dict[str, RecordingSession] = {}  # session_id -> recording session
        self.recording_sessions_lock = asyncio.Lock()  # 录制会话操作的异步锁
        
        # 设备锁定管理（简化版，不依赖外部组件）
        self.device_locks: Dict[str, dict] = {}  # device_serial -> lock_info
        self.device_lock_mutex = threading.Lock()  # 设备锁定操作的线程同步锁
        
        # 配置开关
        self.use_threaded_recording = os.getenv('DROIDBOT_THREADED_RECORDING', 'false').lower() == 'true'
        self.logger.info(f"TaskRecordService initialized with threaded_recording={self.use_threaded_recording}")

    async def _send_session_event(
        self,
        websocket: WebSocket,
        *,
        scope: str,
        code: str,
        message: str,
        close_code: int = 4001,
    ):
        try:
            await websocket.send_json({
                "type": "session_event",
                "scope": scope,
                "code": code,
                "message": message,
                "timestamp": time.time(),
            })
        finally:
            try:
                await websocket.close(code=close_code)
            except Exception:
                pass

    async def _authenticate_websocket_init(self, websocket: WebSocket, device_serial: str) -> dict:
        try:
            init_message = await asyncio.wait_for(websocket.receive_json(), timeout=WEBSOCKET_PONG_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise app_error(401, "AUTH_EXPIRED", "WebSocket auth_init timed out") from exc

        if not isinstance(init_message, dict) or init_message.get("type") != "auth_init":
            raise app_error(401, "AUTH_EXPIRED", "First WebSocket message must be auth_init")

        access_token = init_message.get("access_token")
        workspace_id = init_message.get("workspace_id")
        if not access_token:
            raise app_error(401, "AUTH_EXPIRED", "Access token is required for device connection")
        if not workspace_id:
            raise app_error(409, "WORKSPACE_EXPIRED", "Workspace is required for device connection")

        creator = await asyncio.to_thread(resolve_recording_creator_from_token, access_token)
        device_session = await workspace_state_manager.create_device_session(
            workspace_id=workspace_id,
            user_id=creator["id"],
            device_serial=device_serial,
        )
        return {
            "creator": creator,
            "workspace_id": workspace_id,
            "device_session_id": device_session.device_session_id,
        }

    async def _ensure_runtime_alive_for_device(self, device_serial: str) -> bool:
        async with self.recording_sessions_lock:
            device_sessions = [
                session for session in self.recording_sessions.values()
                if session.device_serial == device_serial
            ]

        for recording_session in device_sessions:
            try:
                await workspace_state_manager.require_runtime_session(recording_session.session_id)
            except AppError as exc:
                await self.broadcast_to_device_clients(device_serial, {
                    "type": "session_event",
                    "scope": "runtime",
                    "code": exc.code,
                    "message": exc.detail,
                    "timestamp": time.time(),
                })
                await self.stop_recording(device_serial, {
                    "session_id": recording_session.session_id,
                    "stop_reason": STOP_REASON_EXPIRED_CLEANUP,
                })
                return False
        return True

    def _scope_for_app_error(self, exc: AppError) -> str:
        if exc.code == "AUTH_EXPIRED":
            return "auth"
        if exc.code.startswith("WORKSPACE"):
            return "workspace"
        if exc.code.startswith("DEVICE"):
            return "device"
        if exc.code.startswith("RECORDING_RUNTIME"):
            return "runtime"
        return "workspace"

    async def _broadcast_session_event(
        self,
        device_serial: str,
        *,
        scope: str,
        code: str,
        message: str,
    ) -> None:
        await self.broadcast_to_device_clients(
            device_serial,
            {
                "type": "session_event",
                "scope": scope,
                "code": code,
                "message": message,
                "timestamp": time.time(),
            },
        )

    async def _handle_runtime_expiry(
        self,
        device_serial: str,
        runtime_id: Optional[str],
        exc: AppError,
    ) -> None:
        await self._broadcast_session_event(
            device_serial,
            scope="runtime",
            code=exc.code,
            message=exc.detail,
        )
        if runtime_id:
            await self.stop_recording(
                device_serial,
                {"session_id": runtime_id, "stop_reason": STOP_REASON_EXPIRED_CLEANUP},
            )
    
    # ========== WebSocket连接管理 ==========
    
    async def connect_device_stream(self, device_serial: str, websocket: WebSocket):
        """连接到设备屏幕流 - 独立的设备连接管理"""
        await websocket.accept()

        try:
            auth_context = await self._authenticate_websocket_init(websocket, device_serial)
        except AppError as exc:
            scope = "auth" if exc.code == "AUTH_EXPIRED" else "workspace"
            await self._send_session_event(websocket, scope=scope, code=exc.code, message=exc.detail)
            return
        except ValueError as exc:
            await self._send_session_event(websocket, scope="auth", code="AUTH_EXPIRED", message=str(exc))
            return

        client_id = f"client_{id(websocket)}_{int(time.time())}"
        device_session_id = auth_context["device_session_id"]
        lock_success = self._try_lock_device(device_serial, client_id, device_session_id)

        if not lock_success:
            await workspace_state_manager.release_device_session(device_session_id, status="disconnected")
            await self._send_session_event(
                websocket,
                scope="device",
                code="DEVICE_LOCK_CONFLICT",
                message=f"Device {device_serial} is currently in use by another client",
                close_code=4000,
            )
            return

        connection_info = {
            'websocket': websocket,
            'client_id': client_id,
            'session_id': device_session_id,
            'device_session_id': device_session_id,
            'workspace_id': auth_context["workspace_id"],
            'user_id': auth_context["creator"]["id"],
            'creator': auth_context["creator"],
            'device_serial': device_serial,
            'connected_time': time.time(),
        }

        if device_serial not in self.connections:
            self.connections[device_serial] = set()
        self.connections[device_serial].add(websocket)
        self.connection_clients[id(websocket)] = connection_info

        if device_serial not in self.device_streams:
            try:
                stream = DeviceScreenStream(device_serial, self)
                await stream.start()
                self.device_streams[device_serial] = stream
                self.active_devices.add(device_serial)
                self.logger.info(f"Started screen stream for device {device_serial}")
            except Exception as e:
                self.logger.error(f"Failed to start screen stream for {device_serial}: {e}")
                self._release_device_lock(device_serial, client_id)
                await workspace_state_manager.release_device_session(device_session_id, status="disconnected")
                await self._send_session_event(
                    websocket,
                    scope="device",
                    code="DEVICE_SESSION_EXPIRED",
                    message=f"Failed to connect to device: {str(e)}",
                )
                return

        self.logger.info(f"Client {client_id} connected and locked device {device_serial}")
        
        try:
            await websocket.send_json({
                "type": "connected",
                "device_serial": device_serial,
                "client_id": client_id,
                "device_session_id": device_session_id,
                "workspace_id": auth_context["workspace_id"],
                "timestamp": datetime.now().isoformat()
            })

            last_ping_time = time.time()
            while True:
                try:
                    try:
                        data = await asyncio.wait_for(
                            websocket.receive_json(),
                            timeout=WEBSOCKET_PING_INTERVAL
                        )
                    except asyncio.TimeoutError:
                        try:
                            await workspace_state_manager.require_device_session(device_session_id)
                        except AppError as exc:
                            self.logger.warning(
                                "Device session expired for %s, closing WebSocket", device_serial
                            )
                            await self._send_session_event(
                                websocket,
                                scope="device",
                                code=exc.code,
                                message=exc.detail,
                            )
                            break

                        await workspace_state_manager.touch_device_transport(device_session_id)
                        await self._ensure_runtime_alive_for_device(device_serial)
                        now = time.time()
                        if now - last_ping_time >= WEBSOCKET_PING_INTERVAL:
                            try:
                                await websocket.send_json({
                                    "type": "ping",
                                    "timestamp": now
                                })
                                last_ping_time = now
                                self.logger.debug(f"Sent ping to client {client_id}")
                            except Exception:
                                break
                        continue

                    msg_type = data.get('type', '') if isinstance(data, dict) else ''
                    data["device_session_id"] = device_session_id
                    data["workspace_id"] = auth_context["workspace_id"]
                    data["_creator"] = auth_context["creator"]

                    if msg_type in ('ping', 'pong'):
                        await workspace_state_manager.touch_device_transport(device_session_id)
                    elif msg_type == "runtime_keepalive":
                        await workspace_state_manager.touch_device_activity(device_session_id)
                        runtime_id = data.get("session_id")
                        if runtime_id:
                            try:
                                await workspace_state_manager.touch_runtime_activity(runtime_id)
                            except AppError as exc:
                                if self._scope_for_app_error(exc) == "runtime":
                                    await self._handle_runtime_expiry(device_serial, runtime_id, exc)
                                    continue
                                raise
                    else:
                        await workspace_state_manager.touch_device_activity(device_session_id)
                        if msg_type in {"start_recording", "stop_recording", "pause_recording", "resume_recording", "touch", "swipe", "key", "text"}:
                            try:
                                await workspace_state_manager.touch_workspace_activity(
                                    auth_context["workspace_id"],
                                    user_id=auth_context["creator"]["id"],
                                )
                            except AppError as exc:
                                await self._send_session_event(
                                    websocket,
                                    scope="workspace",
                                    code=exc.code,
                                    message=exc.detail,
                                )
                                break

                    await self.handle_client_message(device_serial, data)
                except WebSocketDisconnect:
                    break
                except AppError as exc:
                    scope = self._scope_for_app_error(exc)
                    if scope == "runtime":
                        await self._handle_runtime_expiry(device_serial, data.get("session_id"), exc)
                        continue
                    await self._send_session_event(websocket, scope=scope, code=exc.code, message=exc.detail)
                    break
                except Exception as e:
                    self.logger.error(f"Error handling client message: {e}")
                    break
                    
        except WebSocketDisconnect:
            pass
        finally:
            await self.disconnect_client(device_serial, websocket)
    
    async def disconnect_client(self, device_serial: str, websocket: WebSocket):
        """断开客户端连接 - 释放设备锁定"""
        t_start = time.time()
        self.logger.info(f"Disconnecting client from device {device_serial}...")

        websocket_id = id(websocket)

        # 获取连接的客户端信息并释放设备锁定
        if websocket_id in self.connection_clients:
            connection_info = self.connection_clients[websocket_id]
            client_id = connection_info['client_id']
            device_session_id = connection_info.get('device_session_id')

            self._release_device_lock(device_serial, client_id)
            self.logger.debug(f"Released device lock for client {client_id} on device {device_serial}")
            if device_session_id:
                await workspace_state_manager.release_device_session(device_session_id, status="disconnected")

            del self.connection_clients[websocket_id]

        t_lock = time.time()
        self.logger.debug(f"Release device lock took {t_lock - t_start:.2f}s")

        # 停止录制会话（如果存在）
        self.logger.debug("Stopping recording sessions...")
        async with self.recording_sessions_lock:
            device_sessions = [s for s in self.recording_sessions.values() if s.device_serial == device_serial]
            for session in device_sessions:
                try:
                    await session.stop(reason=STOP_REASON_DISCONNECT)
                    if session.session_id in self.recording_sessions:
                        del self.recording_sessions[session.session_id]
                    self.logger.debug(f"Stopped recording session {session.session_id} due to disconnect")
                except Exception as e:
                    self.logger.error(f"Error stopping recording session during disconnect: {e}")

        t_sessions = time.time()
        self.logger.info(f"⏱️ Stop recording sessions took {t_sessions - t_lock:.2f}s")

        if device_serial in self.connections:
            self.connections[device_serial].discard(websocket)

            # 如果没有客户端连接了，停止设备流
            if not self.connections[device_serial]:
                self.logger.debug("No more clients, stopping device stream...")
                if device_serial in self.device_streams:
                    await self.device_streams[device_serial].stop()
                    del self.device_streams[device_serial]
                del self.connections[device_serial]
                self.active_devices.discard(device_serial)

        t_total = time.time() - t_start
        self.logger.info(f"Client disconnected from device {device_serial} (total: {t_total:.2f}s)")
    
    async def broadcast_to_device_clients(self, device_serial: str, message: dict):
        """向指定设备的所有客户端广播消息"""
        if device_serial not in self.connections:
            self.logger.warning(f"No connections found for device {device_serial}")
            return

        disconnected = []
        message_type = message.get("type", "unknown")
        for websocket in self.connections[device_serial].copy():
            try:
                await websocket.send_json(message)
                if message_type == "pong":
                    self.logger.debug(f"💓 Pong sent to device {device_serial}")
            except Exception as e:
                self.logger.error(f"Failed to send {message_type} to device {device_serial}: {type(e).__name__}: {e}")
                # 只有在 WebSocket 确实关闭时才移除
                try:
                    # 检查 WebSocket 状态
                    if hasattr(websocket, 'client_state'):
                        from starlette.websockets import WebSocketState
                        if websocket.client_state == WebSocketState.DISCONNECTED:
                            disconnected.append(websocket)
                            self.logger.warning(f"WebSocket confirmed disconnected for device {device_serial}")
                        else:
                            self.logger.warning(f"WebSocket send failed but state is {websocket.client_state}, not removing")
                    else:
                        # 无法确定状态，保守处理，不移除
                        self.logger.warning(f"Cannot determine WebSocket state, not removing")
                except Exception as check_error:
                    self.logger.error(f"Error checking WebSocket state: {check_error}")

        # 清理确认断开的连接
        for websocket in disconnected:
            self.connections[device_serial].discard(websocket)
            self.logger.warning(f"Removed confirmed disconnected websocket for device {device_serial}")

    def _sanitize_message_for_logging(self, message: dict) -> dict:
        """日志脱敏，避免输出 token"""
        if not isinstance(message, dict):
            return message

        sanitized = dict(message)
        for sensitive_key in ("auth_token", "token", "authorization", "Authorization"):
            if sensitive_key in sanitized:
                sanitized[sensitive_key] = "<redacted>"
        return sanitized

    async def _ensure_recording_entry(self, task_id: int, directory_name: str, recorded_by: int):
        """异步确保 recording 元数据存在"""
        await asyncio.to_thread(
            ensure_recording_metadata,
            task_id,
            directory_name,
            recorded_by
        )
    
    async def handle_client_message(self, device_serial: str, message: dict):
        """处理客户端消息（如设备控制指令）"""
        try:
            message_type = message.get("type")
            log_message = self._sanitize_message_for_logging(message)

            # 打印接收到的消息参数（心跳消息使用 DEBUG 级别）
            if message_type == "ping":
                self.logger.debug(f"📩 Received message from device {device_serial}: type={message_type}, params={log_message}")
            else:
                self.logger.info(f"📩 Received message from device {device_serial}: type={message_type}, params={log_message}")

            if message_type == "ping":
                # 心跳检测：收到 ping 后立即回复 pong
                await self.broadcast_to_device_clients(device_serial, {
                    "type": "pong",
                    "timestamp": time.time(),
                    "device_serial": device_serial
                })
                self.logger.debug(f"💓 Heartbeat ping received and pong sent to device {device_serial}")
            elif message_type == "auth_init":
                self.logger.debug("auth_init already handled during WebSocket handshake")
            elif message_type == "start_recording":
                await self.start_recording(device_serial, message)
            elif message_type == "stop_recording":
                await self.stop_recording(device_serial, message)
            elif message_type == "pause_recording":
                await self.pause_recording(device_serial, message)
            elif message_type == "resume_recording":
                await self.resume_recording(device_serial, message)
            elif message_type == "runtime_keepalive":
                runtime_id = message.get("session_id")
                if runtime_id:
                    await workspace_state_manager.touch_runtime_activity(runtime_id)
            elif message_type in ["touch", "swipe", "key", "text"]:
                await self.record_action(device_serial, message)
            else:
                self.logger.warning(f"Unknown message type: {message_type}")
                
        except AppError:
            raise
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
    
    # ========== 设备锁定管理 ==========
    
    def _try_lock_device(self, device_serial: str, client_id: str, session_id: str) -> bool:
        """尝试锁定设备（线程安全版本）"""
        with self.device_lock_mutex:
            if device_serial in self.device_locks:
                # 设备已被锁定
                return False
            
            # 锁定设备
            self.device_locks[device_serial] = {
                'client_id': client_id,
                'session_id': session_id,
                'locked_time': time.time()
            }
            return True
    
    def _release_device_lock(self, device_serial: str, client_id: str):
        """释放设备锁定（线程安全版本）"""
        with self.device_lock_mutex:
            if device_serial in self.device_locks:
                lock_info = self.device_locks[device_serial]
                if lock_info['client_id'] == client_id:
                    del self.device_locks[device_serial]
    
    # ========== 录制会话管理 ==========
    
    async def start_recording(self, device_serial: str, message: dict):
        """启动Thread+Queue录制会话（线程安全版本）"""
        try:
            async with self.recording_sessions_lock:
                recording_mode = message.get("recording_mode", "new_task")
                views_mode_str = message.get("views_mode", "xml_mode")
                use_image_state = message.get("use_image_state", False)
                auth_token = message.get("auth_token")
                device_session_id = message.get("device_session_id")
                workspace_id = message.get("workspace_id")
                creator = None

                try:
                    views_mode = ViewsMode(views_mode_str)
                except ValueError:
                    # 如果传入的 mode_str 不合法，使用默认模式
                    views_mode = ViewsMode.XML_MODE  
                    self.logger.warning(f"Unknown view mode '{views_mode_str}', fallback to {views_mode.value}")

                # 检查是否已有活跃录制会话
                active_sessions = [s for s in self.recording_sessions.values() if s.device_serial == device_serial and s.is_alive()]
                if active_sessions:
                    await self.broadcast_to_device_clients(device_serial, {
                        "type": "recording_error",
                        "message": "Recording is already active for this device"
                    })
                    return None

                # 根据录制模式确定输出目录和数据集
                if recording_mode == "new_task":
                    # 新建任务模式
                    task_id = message.get("task_id", "manual_recording")

                    try:
                        task_id_int = int(task_id)
                    except (TypeError, ValueError):
                        await self.broadcast_to_device_clients(device_serial, {
                            "type": "recording_error",
                            "message": "Invalid task ID for authenticated recording"
                        })
                        return None

                    try:
                        if message.get("_creator"):
                            creator = dict(message["_creator"])
                        elif auth_token:
                            creator = await asyncio.to_thread(resolve_recording_creator_from_token, auth_token)
                        elif message.get("user_id"):
                            creator = await asyncio.to_thread(resolve_recording_creator_from_user_id, int(message["user_id"]))
                        else:
                            raise ValueError("Authentication required for new task recording. Please refresh and log in again.")
                        await asyncio.to_thread(validate_recording_creator_access, task_id_int, creator)
                    except ValueError as e:
                        await self.broadcast_to_device_clients(device_serial, {
                            "type": "recording_error",
                            "message": str(e)
                        })
                        return None

                    from backend.config import Config

                    output_dir = self._generate_output_dir(task_id)
                    dataset = Path(output_dir).resolve().relative_to(Config.DATA_DIR.resolve()).as_posix()
                elif recording_mode == "append_data":
                    # 追加数据模式
                    dataset = message.get("dataset")
                    if not dataset:
                        await self.broadcast_to_device_clients(device_serial, {
                            "type": "recording_error",
                            "message": "Dataset name is required for append mode"
                        })
                        return None

                    # 使用已存在的 dataset 路径
                    from backend.config import Config
                    output_dir = Config.DATA_DIR / dataset

                    if not output_dir.exists():
                        await self.broadcast_to_device_clients(device_serial, {
                            "type": "recording_error",
                            "message": f"Dataset directory does not exist: {dataset}"
                        })
                        return None

                    output_dir = str(output_dir)
                    task_id = None  # 追加模式不需要 task_id
                else:
                    await self.broadcast_to_device_clients(device_serial, {
                        "type": "recording_error",
                        "message": f"Unknown recording mode: {recording_mode}"
                    })
                    return None

                self.logger.info(f"Starting recording for device {device_serial}, task: {task_id}, dataset: {dataset}, views_mode: {views_mode}, use_image_state: {use_image_state}, recording_mode: {recording_mode}")

                # 创建新的录制会话
                session = RecordingSession(
                    device_serial,
                    output_dir,
                    dataset,
                    task_id,
                    views_mode,
                    use_image_state,
                    recording_mode,
                    self,
                    creator_user_id=creator["id"] if creator else None
                )

                if not device_session_id or not workspace_id:
                    await self.broadcast_to_device_clients(device_serial, {
                        "type": "recording_error",
                        "message": "Missing WebSocket device session context"
                    })
                    return None

                try:
                    await workspace_state_manager.create_runtime_session(
                        recording_runtime_id=session.session_id,
                        device_session_id=device_session_id,
                        workspace_id=workspace_id,
                        task_id=str(task_id) if task_id else None,
                        directory_name=dataset,
                        recorded_by=creator["id"] if creator else None,
                    )
                except AppError as exc:
                    await self.broadcast_to_device_clients(device_serial, {
                        "type": "session_event",
                        "scope": "runtime" if exc.code.startswith("RECORDING_RUNTIME") else "device",
                        "code": exc.code,
                        "message": exc.detail,
                        "timestamp": time.time(),
                    })
                    return None
                
                # 启动会话
                if session.start():
                    # 添加到会话管理字典
                    self.recording_sessions[session.session_id] = session
                    self.logger.info(f"Recording session started: {session.session_id}")

                    # 更新任务状态为 in_progress（仅 new_task 模式）
                    if recording_mode == "new_task" and task_id:
                        try:
                            update_task_status(int(task_id), "in_progress")
                            self.logger.info(f"Task {task_id} status updated to in_progress")
                        except Exception as e:
                            self.logger.warning(f"Failed to update task status: {e}")

                    return session.session_id
                else:
                    await workspace_state_manager.release_runtime_session(session.session_id, status="failed")
                    error_message = {
                        "type": "recording_error",
                        "message": "Failed to start recording session"
                    }
                    
                    await self.broadcast_to_device_clients(device_serial, error_message)
                    return None
                    
        except Exception as e:
            self.logger.error(f"Failed to start recording: {e}")
            await self.broadcast_to_device_clients(device_serial, {
                "type": "recording_error",
                "message": f"Failed to start recording: {str(e)}"
            })
            return None
            
    async def stop_recording(self, device_serial: str, message: dict):
        """停止录制会话（线程安全版本）"""
        try:
            t_start = time.time()
            self.logger.info(f"Stopping recording for device {device_serial}...")

            async with self.recording_sessions_lock:
                session_id = message.get("session_id")
                stop_reason = message.get("stop_reason", STOP_REASON_USER)

                # 查找要停止的会话
                target_session = None
                if session_id and session_id in self.recording_sessions:
                    target_session = self.recording_sessions[session_id]
                else:
                    # 查找该设备的任何活跃会话
                    active_sessions = [
                        s for s in self.recording_sessions.values()
                        if s.device_serial == device_serial and s.is_alive()
                    ]
                    if active_sessions:
                        # 使用最新的会话
                        target_session = max(active_sessions, key=lambda s: s.created_time)

                if not target_session:
                    error_message = {
                        "type": "recording_error",
                        "message": "No active recording session found for this device"
                    }

                    await self.broadcast_to_device_clients(device_serial, error_message)
                    return 0

                t_find = time.time()
                self.logger.debug(f"Found target session in {t_find - t_start:.2f}s")

                # 停止会话
                self.logger.debug("Calling session.stop()...")
                try:
                    await workspace_state_manager.set_runtime_state(target_session.session_id, "stopping")
                except AppError:
                    pass
                action_count = await target_session.stop(reason=stop_reason)
                t_stop = time.time()
                self.logger.info(f"⏱️ session.stop() took {t_stop - t_find:.2f}s")

                # 从会话字典中移除
                if target_session.session_id in self.recording_sessions:
                    del self.recording_sessions[target_session.session_id]
                try:
                    await workspace_state_manager.release_runtime_session(target_session.session_id, status="stopped")
                except AppError:
                    pass

                # 只有用户显式停止录制时，new_task 才进入 completed
                if (
                    stop_reason == STOP_REASON_USER and
                    target_session.recording_mode == "new_task" and
                    target_session.user_task_id
                ):
                    try:
                        update_task_status(int(target_session.user_task_id), "completed")
                        self.logger.info(f"Task {target_session.user_task_id} status updated to completed")
                    except Exception as e:
                        self.logger.warning(f"Failed to update task status: {e}")

                response_message = {
                    "type": "recording_stopped",
                    "device_serial": device_serial,
                    "session_id": target_session.session_id,
                    "task_id": target_session.user_task_id,
                    "action_count": action_count,
                    "timestamp": datetime.now().isoformat(),
                    "architecture": "threaded_independent"
                }

                await self.broadcast_to_device_clients(device_serial, response_message)

                t_total = time.time() - t_start
                self.logger.info(f"Recording stopped: {target_session.session_id}, actions: {action_count} (total: {t_total:.2f}s)")
                return action_count
                
        except Exception as e:
            self.logger.error(f"Failed to stop recording: {e}")
            await self.broadcast_to_device_clients(device_serial, {
                "type": "recording_error",
                "message": f"Failed to stop recording: {str(e)}"
            })
            return 0

    async def pause_recording(self, device_serial: str, message: dict):
        """暂停录制会话"""
        try:
            async with self.recording_sessions_lock:
                target_session = self._find_target_session(device_serial, message.get("session_id"))

                if not target_session:
                    await self.broadcast_to_device_clients(device_serial, {
                        "type": "recording_error",
                        "message": "No active recording session found for this device"
                    })
                    return False

                await workspace_state_manager.set_runtime_state(target_session.session_id, "paused")
                await target_session.pause()
                return True
        except AppError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to pause recording: {e}")
            await self.broadcast_to_device_clients(device_serial, {
                "type": "recording_error",
                "message": f"Failed to pause recording: {str(e)}"
            })
            return False

    async def resume_recording(self, device_serial: str, message: dict):
        """恢复录制会话"""
        try:
            async with self.recording_sessions_lock:
                target_session = self._find_target_session(device_serial, message.get("session_id"))

                if not target_session:
                    await self.broadcast_to_device_clients(device_serial, {
                        "type": "recording_error",
                        "message": "No active recording session found for this device"
                    })
                    return False

                await workspace_state_manager.set_runtime_state(target_session.session_id, "recording")
                await target_session.resume()
                return True
        except AppError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to resume recording: {e}")
            await self.broadcast_to_device_clients(device_serial, {
                "type": "recording_error",
                "message": f"Failed to resume recording: {str(e)}"
            })
            return False
            
    async def record_action(self, device_serial: str, action: dict):
        """记录用户操作到指定会话（线程安全版本）"""
        try:
            async with self.recording_sessions_lock:
                target_session = self._find_target_session(device_serial, action.get("session_id"))

                if target_session:
                    await workspace_state_manager.touch_runtime_activity(target_session.session_id)
                    await target_session.record_action(action)
                    self.logger.debug(
                        f"Action recorded to session {target_session.session_id}"
                    )
                    return True
                
                self.logger.warning(f"No active session found for device {device_serial}")
                return False
        except AppError:
            raise
        except Exception as e:
            self.logger.error(f"Error recording action: {e}")
            return False
    
    # ========== 服务管理 ==========
            
    async def cleanup_dead_sessions(self) -> int:
        """清理死亡的录制线程会话（线程安全版本）"""
        async with self.recording_sessions_lock:
            dead_sessions = [
                session_id for session_id, session in self.recording_sessions.items() 
                if not session.is_alive()
            ]
            
            for session_id in dead_sessions:
                session_info = self.recording_sessions[session_id].get_session_info()
                del self.recording_sessions[session_id]
                self.logger.info(f"Cleaned up dead session: {session_id} for device {session_info['device_serial']}")
                
            return len(dead_sessions)
        
    async def get_active_sessions(self) -> Dict[str, dict]:
        """获取所有活跃会话信息（线程安全版本）"""
        async with self.recording_sessions_lock:
            active_sessions = {}
            for session_id, session in self.recording_sessions.items():
                if session.is_alive():
                    active_sessions[session_id] = session.get_session_info()
            return active_sessions
        
    async def get_session_info(self, session_id: str) -> dict:
        """获取指定会话信息（线程安全版本）"""
        async with self.recording_sessions_lock:
            if session_id in self.recording_sessions:
                return self.recording_sessions[session_id].get_session_info()
            return {}

    def _find_target_session(self, device_serial: str, session_id: Optional[str] = None):
        """优先按 session_id 查找会话，否则返回该设备最新活跃会话"""
        if session_id and session_id in self.recording_sessions:
            session = self.recording_sessions[session_id]
            if session.device_serial == device_serial and session.is_alive():
                return session

        active_sessions = [
            s for s in self.recording_sessions.values()
            if s.device_serial == device_serial and s.is_alive()
        ]
        if not active_sessions:
            return None

        return max(active_sessions, key=lambda s: s.created_time)
        
    def is_threaded_recording_enabled(self) -> bool:
        """检查是否启用了Thread+Queue录制"""
        return self.use_threaded_recording

    def _sanitize_task_description(self, raw_description: str, task_id: str) -> str:
        """清理任务描述并控制字节长度"""
        # 移除不允许的字符并标准化空白
        clean_description = re.sub(r'[<>:"/\\|?*]', '', raw_description or '')
        clean_description = clean_description.replace(' ', '_')
        clean_description = re.sub(r'_+', '_', clean_description).strip('_')

        if not clean_description:
            clean_description = f"task_{task_id}"

        encoded = clean_description.encode('utf-8')
        if len(encoded) > MAX_RECORDING_DESCRIPTION_BYTES:
            truncated = encoded[:MAX_RECORDING_DESCRIPTION_BYTES]
            clean_description = truncated.decode('utf-8', errors='ignore').rstrip('_-.')
            if not clean_description:
                clean_description = f"task_{task_id}"

        return clean_description

    def _build_timestamp_unique_suffix(self) -> str:
        """生成统一的时间戳+唯一标识后缀"""
        now = datetime.now()
        timestamp = f"{now.strftime('%y%m%d')}_{now.strftime('%H%M%S')}_{now.microsecond:06d}"
        unique_code = uuid.uuid4().hex[:8]
        return f"{timestamp}_{unique_code}"
        
    def _generate_output_dir(self, task_id: str) -> str:
        """生成输出目录路径"""
        try:
            if task_id and task_id != "manual_recording":
                task_description = self._get_task_description(task_id)
                clean_description = self._sanitize_task_description(task_description, task_id)
                unique_suffix = self._build_timestamp_unique_suffix()
                output_dir_name = f"task_{task_id}_{clean_description}_{unique_suffix}"
            else:
                # 手动录制
                unique_suffix = self._build_timestamp_unique_suffix()
                output_dir_name = f"manual_recording_{unique_suffix}"
            
            # 使用配置的 RECORD_DIR 而不是硬编码路径
            from backend.config import Config
            output_dir = Config.RECORD_DIR / output_dir_name
            
            # 创建目录
            output_dir.mkdir(parents=True, exist_ok=True)
            
            return str(output_dir)
            
        except Exception as e:
            self.logger.error(f"Error generating output directory: {e}")
            # 后备目录
            from backend.config import Config
            fallback_dir = Config.RECORD_DIR / "fallback"
            fallback_dir.mkdir(parents=True, exist_ok=True)

            fallback_suffix = self._build_timestamp_unique_suffix()
            unique_fallback = fallback_dir / f"fallback_recording_{fallback_suffix}"
            unique_fallback.mkdir(parents=True, exist_ok=True)
            return str(unique_fallback)
            
    def _get_task_description(self, task_id: str) -> str:
        """获取任务描述（从数据库查询）"""
        try:
            from backend.database import engine
            from backend.models.task import Task
            from sqlmodel import Session

            with Session(engine) as session:
                task = session.get(Task, int(task_id))
                if task:
                    return task.description

            return f"task_{task_id}"

        except Exception as e:
            self.logger.error(f"Failed to get task description: {e}")
            return f"task_{task_id}"


# 全局任务录制服务实例
task_record_service = TaskRecordService()
