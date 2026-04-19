"""
RecordingWorkerThread - 专门的录制工作线程
在独立线程中管理Device和UTG，通过队列接收操作事件
"""

import logging
import queue
import threading
import time
from droidbot.constant import ViewsMode


class RecordingWorkerThread(threading.Thread):
    """专门的录制工作线程"""
    
    def __init__(self, device_serial: str, output_dir: str, views_mode: ViewsMode,
                 event_queue: queue.Queue, response_queue: queue.Queue, dataset: str, 
                 use_image_state: bool = False, recording_mode: str = "new_task", 
                 task_id: str = None):
        super().__init__(name=f"RecordingWorker-{device_serial}")
        self.device_serial = device_serial
        self.output_dir = output_dir
        self.views_mode = views_mode
        self.use_image_state = use_image_state
        self.dataset = dataset  # 数据集名称，用于UTG缓存管理
        self.recording_mode = recording_mode  # 录制模式：new_task 或 append_data
        self.task_id = task_id  # 任务ID，用于创建task-info.yaml
        self.event_queue = event_queue
        self.response_queue = response_queue
        self.logger = logging.getLogger(f"{__name__}.{device_serial}")

        # 核心组件（在线程中初始化）
        self.device = None
        self.utg_service = None  # UTGServiceV2引用
        self.app = None

        # 状态管理 - 延迟记录模式
        self.enabled = False
        self.last_state = None
        self.last_event = None
        self.event_count = 0
        self.is_paused = False

        # 注意：_init_device_and_utg() 移到 run() 中执行，避免阻塞事件循环

    def run(self):
        """主工作循环"""
        try:
            # 在线程中初始化设备和UTG，避免阻塞主事件循环
            self._init_device_and_utg()

            self.enabled = True
            self._signal_ready()
            
            self.logger.debug(f"Recording worker thread started for device {self.device_serial}")
            
            # 主事件处理循环
            while self.enabled:
                try:
                    event = self.event_queue.get(timeout=1.0)

                    event_type = event.get("type")
                    if event_type == "shutdown":
                        self._handle_shutdown()
                        break
                    elif event_type == "pause_recording":
                        self._handle_pause()
                    elif event_type == "resume_recording":
                        self._handle_resume()
                    else:
                        self._handle_event(event)
                        
                except queue.Empty:
                    continue  # 超时继续等待
                    
        except Exception as e:
            self.logger.error(f"Recording thread fatal error: {e}")
            self._signal_error(str(e))
        finally:
            self._cleanup_resources()
            
    def _init_device_and_utg(self):
        """在工作线程中初始化Device和UTG，通过UTGServiceV2管理"""
        try:
            # 初始化Device
            from droidbot.device import Device
            self.device = Device(
                device_serial=self.device_serial,
                output_dir=self.output_dir,
                views_mode=self.views_mode,
                use_image_state=self.use_image_state
            )
            
            # 连接设备
            self.device.connect()
            self.logger.debug(f"Device connected: {self.device_serial} with views_mode={self.views_mode}, use_image_state={self.use_image_state}")
            
            # 获取设备信息
            device_info = {
                'serial': self.device.serial,
                'model_number': self.device.get_model_number(),
                'sdk_version': self.device.get_sdk_version()
            }
            
            # 初始化应用上下文
            from droidbot.app import DummyApp
            self.app = DummyApp()
            app_info = {
                'package_name': self.app.package_name,
                'main_activity': self.app.main_activity,
                'activities': self.app.activities
            }
            
            # 导入UTGServiceV2
            from .utg_service_v2 import UTGServiceV2
            self.utg_service = UTGServiceV2

            # 根据录制模式决定是否创建新的UTG
            try:
                if self.recording_mode == "new_task":
                    # 新建任务模式：创建新的UTG
                    self.logger.debug(f"New task mode: creating new UTG for dataset '{self.dataset}'")
                    result = self.utg_service.create_new_utg_sync(
                        dataset=self.dataset,
                        device_info=device_info,
                        app_info=app_info,
                        output_dir=self.output_dir
                    )
                    self.logger.debug(f"Created new UTG for dataset '{self.dataset}': {result['message']}")

                    # 创建 task-info.yaml（仅在 new_task 模式下）
                    if self.task_id:
                        try:
                            from .task_service import TaskService

                            # 创建 task-info.yaml，description 会自动从 CSV 获取
                            TaskService.create_task_info(
                                recording_name=self.dataset,
                                task_id=self.task_id
                            )
                            self.logger.debug(f"Created task-info.yaml for dataset '{self.dataset}' with task_id '{self.task_id}'")
                        except FileExistsError:
                            # 已存在，跳过
                            self.logger.debug(f"Task-info already exists for dataset '{self.dataset}'")
                        except Exception as e:
                            # task-info 创建失败不影响录制，只记录错误
                            self.logger.error(f"Failed to create task-info: {e}")
                    else:
                        self.logger.warning("No task_id provided, skipping task-info creation")

                elif self.recording_mode == "append_data":
                    # 追加数据模式：直接加载已有UTG（由UTGServiceV2自动管理）
                    self.logger.debug(f"Append data mode: will use existing UTG for dataset '{self.dataset}'")
                else:
                    raise ValueError(f"Unknown recording mode: {self.recording_mode}")
            except Exception as e:
                self.logger.error(f"Failed to initialize UTG via service: {e}")
                raise
            
            self.logger.debug("Device and UTG initialized successfully via UTGServiceV2")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize device and UTG: {e}")
            raise
            
    def _signal_ready(self):
        """向主线程发送准备完成信号"""
        try:
            self.response_queue.put({
                "type": "recording_ready",
                "device_serial": self.device_serial,
                "timestamp": time.time()
            })
        except Exception as e:
            self.logger.error(f"Failed to signal ready: {e}")
            
    def _signal_error(self, error_message: str):
        """向主线程发送错误信号"""
        try:
            self.response_queue.put({
                "type": "error",
                "device_serial": self.device_serial,
                "message": error_message,
                "timestamp": time.time()
            })
        except Exception as e:
            self.logger.error(f"Failed to signal error: {e}")
            
    def _handle_event(self, event_data: dict):
        """处理用户操作事件，实现延迟记录的UTG更新，通过UTGServiceV2"""
        try:
            if self.is_paused:
                self._execute_unrecorded_event(event_data)
            else:
                self._execute_recorded_event(event_data)
        except Exception as e:
            self.logger.error(f"Error handling event: {e}")
            
            # 发送错误反馈
            try:
                self.response_queue.put({
                    "type": "event_error",
                    "device_serial": self.device_serial,
                    "operation_type": event_data.get("type"),
                    "operation_data": {
                        key: value for key, value in event_data.items() 
                        if key not in ["timestamp", "session_id"]
                    },
                    "recorded": False,
                    "recording_state": "paused" if self.is_paused else "recording",
                    "error_message": str(e),
                    "timestamp": time.time()
                })
            except Exception as queue_error:
                self.logger.error(f"Failed to send error feedback: {queue_error}")

    def _execute_recorded_event(self, event_data: dict):
        """执行并记录一个事件"""
        t_start = time.time()
        current_state = self.device.get_current_state()
        t_get_state = time.time()
        self.logger.info(f"⏱️ get_current_state took {t_get_state - t_start:.2f}s")

        is_segment_start = self.last_event is None and self.last_state is None
        self._flush_pending_recorded_transition(current_state)
        if is_segment_start:
            self._sync_segment_start_state(current_state)

        input_event = self._create_input_event(event_data)
        if not input_event:
            return

        t_send_start = time.time()
        self.device.send_event(input_event)
        t_send_end = time.time()
        self.logger.info(f"⏱️ send_event took {t_send_end - t_send_start:.2f}s")

        self.last_state = current_state
        self.last_event = input_event
        self.event_count += 1

        t_total = time.time() - t_start
        self.logger.info(
            f"Event {self.event_count} executed: {input_event.__class__.__name__} "
            f"(total: {t_total:.2f}s)"
        )

        self._queue_event_feedback(event_data, recorded=True)

    def _execute_unrecorded_event(self, event_data: dict):
        """执行事件但不写入录制结果"""
        t_start = time.time()
        input_event = self._create_input_event(event_data)
        if not input_event:
            return

        t_send_start = time.time()
        self.device.send_event(input_event)
        t_send_end = time.time()
        self.logger.info(f"⏱️ send_event took {t_send_end - t_send_start:.2f}s")

        t_total = time.time() - t_start
        self.logger.info(
            f"Paused event executed without recording: {input_event.__class__.__name__} "
            f"(total: {t_total:.2f}s)"
        )

        self._queue_event_feedback(event_data, recorded=False)

    def _flush_pending_recorded_transition(self, current_state=None):
        """记录上一个已录制事件的状态转换"""
        if not (self.last_event and self.last_state):
            return current_state

        if current_state is None and self.device:
            current_state = self.device.get_current_state()

        if not current_state:
            return current_state

        try:
            t_transition_start = time.time()
            transition_result = self.utg_service.add_transition_sync(
                self.last_event,
                self.last_state,
                current_state,
                self.dataset
            )
            t_transition_end = time.time()
            self.logger.info(
                f"⏱️ add_transition_sync took {t_transition_end - t_transition_start:.2f}s"
            )

            if transition_result['success']:
                self.logger.debug(
                    "UTG transition recorded via UTGServiceV2: "
                    f"{self.last_state.foreground_activity} -> {current_state.foreground_activity}"
                )
            else:
                self.logger.debug(
                    "UTG transition was ineffective (self-loop): "
                    f"{self.last_state.foreground_activity}"
                )
        except Exception as utg_error:
            self.logger.error(f"Failed to record UTG transition: {utg_error}")

        return current_state

    def _sync_segment_start_state(self, state):
        """在录制段起点先持久化当前页面节点"""
        if not state or not self.utg_service:
            return

        try:
            if hasattr(self.utg_service, "sync_state_node_sync"):
                self.utg_service.sync_state_node_sync(state, self.dataset)
        except Exception as sync_error:
            self.logger.warning(f"Failed to sync segment start state: {sync_error}")

    def _queue_event_feedback(self, event_data: dict, recorded: bool):
        """发送操作执行反馈"""
        self.response_queue.put({
            "type": "event_completed",
            "device_serial": self.device_serial,
            "event_count": self.event_count,
            "operation_type": event_data.get("type"),
            "operation_data": {
                key: value for key, value in event_data.items()
                if key not in ["timestamp", "session_id"]
            },
            "recorded": recorded,
            "recording_state": "paused" if self.is_paused else "recording",
            "timestamp": time.time()
        })

    def _handle_pause(self):
        """暂停录制并切断当前录制段"""
        if not self.is_paused:
            self._flush_pending_recorded_transition()
            self.last_state = None
            self.last_event = None
            self.is_paused = True

        self.response_queue.put({
            "type": "recording_paused",
            "device_serial": self.device_serial,
            "event_count": self.event_count,
            "timestamp": time.time()
        })

    def _handle_resume(self):
        """恢复录制"""
        self.is_paused = False
        self.response_queue.put({
            "type": "recording_resumed",
            "device_serial": self.device_serial,
            "event_count": self.event_count,
            "timestamp": time.time()
        })
            
    def _create_input_event(self, event_data: dict):
        """从事件数据创建InputEvent对象"""
        try:
            event_type = event_data.get("type")
            
            if event_type == "touch":
                return self._create_touch_event(event_data)
            elif event_type == "swipe":
                return self._create_swipe_event(event_data)
            elif event_type == "key":
                return self._create_key_event(event_data)
            elif event_type == "text":
                return self._create_text_event(event_data)
            else:
                self.logger.warning(f"Unknown event type: {event_type}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error creating input event: {e}")
            return None
            
    def _create_touch_event(self, event_data: dict):
        """创建触摸事件"""
        from droidbot.input_event import TouchEvent
        
        x = event_data.get("x")
        y = event_data.get("y")
        if x is not None and y is not None:
            # 转换相对坐标到绝对坐标
            abs_x, abs_y = self._convert_relative_to_absolute(x, y)
            
            matching_views = self.device.get_view_by_coordinates(abs_x, abs_y, is_visible=True, is_clickable=True)

            if len(matching_views) > 0:
                return TouchEvent(x=abs_x, y=abs_y, view=matching_views[0])

            return TouchEvent(x=abs_x, y=abs_y)

        return None
        
    def _create_swipe_event(self, event_data: dict):
        """创建滑动事件"""
        from droidbot.input_event import SwipeEvent
        
        start_x = event_data.get("start_x")
        start_y = event_data.get("start_y")
        end_x = event_data.get("end_x")
        end_y = event_data.get("end_y")
        
        if all(v is not None for v in [start_x, start_y, end_x, end_y]):
            # 转换相对坐标到绝对坐标
            abs_start_x, abs_start_y = self._convert_relative_to_absolute(start_x, start_y)
            abs_end_x, abs_end_y = self._convert_relative_to_absolute(end_x, end_y)
            
             # 获取滑动起始位置的视图信息
            start_matching_views = self.device.get_view_by_coordinates(abs_start_x, abs_start_y, is_visible=True, is_scrollable=True)
            end_matching_views = self.device.get_view_by_coordinates(abs_end_x, abs_end_y, is_visible=True, is_scrollable=True)
   
            start_view = start_matching_views[0] if len(start_matching_views) > 0 else None
            end_view = end_matching_views[0] if len(end_matching_views) > 0 else None

            return SwipeEvent(
                start_x=abs_start_x, start_y=abs_start_y, start_view=start_view,
                end_x=abs_end_x, end_y=abs_end_y, end_view=end_view,
            )

        return None
        
    def _create_key_event(self, event_data: dict):
        """创建按键事件"""
        from droidbot.input_event import KeyEvent
        
        key_code = event_data.get("key_code")
        if key_code:
            return KeyEvent(name=key_code)
        return None
        
    def _create_text_event(self, event_data: dict):
        """创建文本输入事件"""
        from droidbot.input_event import PutTextEvent
        
        text = event_data.get("text")
        if text:
            return PutTextEvent(text=text)
        return None
        
    def _convert_relative_to_absolute(self, rel_x: int, rel_y: int) -> tuple[int, int]:
        """转换相对坐标到绝对坐标
        
        Args:
            rel_x: 相对X坐标 (0-1000)
            rel_y: 相对Y坐标 (0-1000)  
            
        Returns:
            绝对坐标像素值元组 (absolute_x, absolute_y)
        """
        try:
            # 获取设备尺寸
            device_width = self.device.get_width(refresh=True)
            device_height = self.device.get_height(refresh=False)
            
            # 转换相对坐标到绝对像素
            # 前端使用0-1000的相对坐标
            abs_x = int(rel_x * device_width / 1000)
            abs_y = int(rel_y * device_height / 1000)
            
            self.logger.debug(f"Converted coordinates: ({rel_x},{rel_y}) -> ({abs_x},{abs_y}) for device {device_width}x{device_height}")
            return abs_x, abs_y
                
        except Exception as e:
            self.logger.error(f"Error converting coordinates: {e}")
            # 后备：直接使用相对值
            return int(rel_x), int(rel_y)
            
    def _handle_shutdown(self):
        """处理关闭信号，保存最终UTG状态"""
        try:
            self.enabled = False
            self.logger.debug("Received shutdown signal")

            # 记录最后的状态转换
            if self.device and self.last_event and self.last_state:
                try:
                    final_state = self._flush_pending_recorded_transition()
                    if final_state:
                        self.logger.debug(
                            "Final UTG transition recorded via shutdown: "
                            f"{self.last_state.foreground_activity} -> {final_state.foreground_activity}"
                        )
                except Exception as e:
                    self.logger.warning(f"Failed to record final transition: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            
    def _cleanup_resources(self):
        """清理资源"""
        try:
            # 断开设备连接
            if self.device:
                self.device.disconnect()
                self.logger.debug("Device disconnected")

            self.logger.debug(f"Recording worker thread stopped. Total events: {self.event_count}")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
