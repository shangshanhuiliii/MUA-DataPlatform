import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..config import Config
from ..schemas.utg import NodeDelete
from ..utils.validation import ValidationUtils

logger = logging.getLogger(__name__)


@dataclass
class UTGCacheEntry:
    """UTG缓存条目，包含UTG对象和元数据"""
    utg_object: Any  # droidbot.utg.UTG对象实例
    dataset: str  # 数据集名称
    load_time: float  # 加载时间戳
    last_access_time: float  # 最后访问时间戳
    access_count: int  # 访问计数
    file_mtime: float  # utg.json文件修改时间
    lock: threading.RLock = None  # UTG对象操作锁

    def __post_init__(self):
        """初始化锁对象"""
        if self.lock is None:
            self.lock = threading.RLock()
    
    def touch(self):
        """更新最后访问时间和访问计数"""
        self.last_access_time = time.time()
        self.access_count += 1
    
    def update_mtime(self, new_mtime: float):
        """更新文件修改时间（内部编辑操作后调用）"""
        self.file_mtime = new_mtime
    
    def is_valid(self, current_mtime: float, ttl: float = 3600) -> bool:
        """检查缓存条目是否有效
        
        Args:
            current_mtime: 当前文件修改时间
            ttl: 生存时间（秒）
            
        Returns:
            bool: 缓存是否有效
        """
        # 检查TTL过期
        if time.time() - self.load_time > ttl:
            return False
        
        # 检查文件是否被外部修改
        if abs(current_mtime - self.file_mtime) > 0.01:  # 允许0.01秒的时间误差
            return False
            
        return True
    
    def get_age(self) -> float:
        """获取缓存条目的年龄（秒）"""
        return time.time() - self.load_time
    
    def get_memory_size_estimate(self) -> int:
        """估算内存使用大小（字节）"""
        # 简单估算，实际大小会更复杂
        base_size = 1024 * 1024  # 1MB基础大小
        try:
            # 使用 UTG 的 property 获取节点和转换数量
            node_count = self.utg_object.num_nodes
            transition_count = self.utg_object.num_transitions
            estimated_size = base_size + (node_count * 50 * 1024) + (transition_count * 10 * 1024)
            return min(estimated_size, 100 * 1024 * 1024)  # 最大100MB
        except Exception:
            return base_size

class UTGServiceV2:
    """UTG操作服务类 V2 - 带智能内存缓存"""
    
    # 类级别缓存管理
    _cache: Dict[str, UTGCacheEntry] = {}
    _cache_lock = threading.RLock()
    _max_cache_size = int(os.getenv('UTG_CACHE_MAX_SIZE', '10'))  # 最大缓存条目数
    _cache_ttl = int(os.getenv('UTG_CACHE_TTL', '3600'))  # 1小时默认TTL
    
    # 性能统计
    _cache_stats = {
        'hits': 0,
        'misses': 0,
        'loads': 0,
        'evictions': 0
    }
    
    @classmethod
    def _get_cache_key(cls, dataset: str) -> str:
        """生成缓存键"""
        return f"utg_{dataset}" if dataset else "utg_default"
    
    @classmethod
    def _get_file_mtime(cls, dataset: str) -> float:
        """获取utg.json文件的修改时间"""
        try:
            utg_path = Config.DATA_DIR / dataset / "utg.json"
            if utg_path.exists():
                return utg_path.stat().st_mtime
            return 0.0
        except Exception as e:
            logger.warning(f"Failed to get mtime for dataset '{dataset}': {e}")
            return 0.0
    
    @classmethod
    def _update_cache_mtime(cls, dataset: str):
        """更新缓存中的文件修改时间（内部编辑操作后调用）"""
        with cls._cache_lock:
            cache_key = cls._get_cache_key(dataset)
            if cache_key in cls._cache:
                new_mtime = cls._get_file_mtime(dataset)
                cls._cache[cache_key].update_mtime(new_mtime)
                logger.debug(f"Updated cache mtime for dataset '{dataset}': {new_mtime}")
    
    @classmethod
    def _cleanup_expired_cache(cls):
        """清理过期的缓存条目"""
        with cls._cache_lock:
            expired_keys = []

            for cache_key, entry in cls._cache.items():
                current_mtime = cls._get_file_mtime(entry.dataset)
                if not entry.is_valid(current_mtime, cls._cache_ttl):
                    expired_keys.append(cache_key)

            # 删除过期条目时，先获取其 UTG 锁，确保没有操作正在进行
            for key in expired_keys:
                entry = cls._cache[key]
                # 获取该条目的锁，等待所有操作完成
                with entry.lock:
                    del cls._cache[key]
                    cls._cache_stats['evictions'] += 1
                    logger.info(f"Evicted expired cache entry: {key}")
    
    @classmethod
    def _enforce_cache_size_limit(cls):
        """执行缓存大小限制，使用LRU策略"""
        with cls._cache_lock:
            while len(cls._cache) > cls._max_cache_size:
                # 找到最久未访问的条目
                oldest_key = min(cls._cache.keys(),
                                key=lambda k: cls._cache[k].last_access_time)
                entry = cls._cache[oldest_key]
                # 获取该条目的锁，等待所有操作完成
                with entry.lock:
                    del cls._cache[oldest_key]
                    cls._cache_stats['evictions'] += 1
                    logger.info(f"Evicted LRU cache entry: {oldest_key}")
    
    @classmethod
    def _get_utg_with_lock(cls, dataset: str):
        """获取UTG对象和对应的锁（用于需要加锁的操作）

        Args:
            dataset: 数据集名称

        Returns:
            tuple: (utg_object, lock) 或 (None, None)
        """
        cache_key = cls._get_cache_key(dataset)

        with cls._cache_lock:
            if cache_key in cls._cache:
                entry = cls._cache[cache_key]
                return entry.utg_object, entry.lock

        # 如果缓存中没有，先加载
        utg = cls._load_utg_object(dataset)
        if utg is None:
            return None, None

        # 加载后再次获取锁
        with cls._cache_lock:
            if cache_key in cls._cache:
                entry = cls._cache[cache_key]
                return entry.utg_object, entry.lock

        return None, None

    @classmethod
    def _load_utg_object(cls, dataset: str):
        """加载UTG对象实例（带智能缓存）

        Args:
            dataset: 数据集名称（必需参数，由路由层从会话传入）
        """
        cache_key = cls._get_cache_key(dataset)
        current_mtime = cls._get_file_mtime(dataset)
        
        # 先清理过期缓存
        cls._cleanup_expired_cache()
        
        with cls._cache_lock:
            # 1. 检查缓存是否存在且有效
            if cache_key in cls._cache:
                entry = cls._cache[cache_key]
                if entry.is_valid(current_mtime, cls._cache_ttl):
                    # 缓存命中
                    entry.touch()
                    cls._cache_stats['hits'] += 1
                    logger.debug(f"Cache hit for dataset '{dataset}' (access #{entry.access_count})")
                    return entry.utg_object
                else:
                    # 缓存失效，删除（先获取锁，等待操作完成）
                    with entry.lock:
                        del cls._cache[cache_key]
                        cls._cache_stats['evictions'] += 1
                        logger.info(f"Cache invalidated for dataset '{dataset}' due to mtime change")
            
            # 2. 缓存未命中，从磁盘加载
            cls._cache_stats['misses'] += 1
            logger.info(f"Cache miss for dataset '{dataset}', loading from disk...")
            
            try:
                # 导入UTG类
                from droidbot.utg import UTG
                
                # 构建数据目录路径
                data_dir = Config.DATA_DIR / dataset
                
                # 检查utg.json是否存在
                utg_json_path = data_dir / "utg.json"
                if not utg_json_path.exists():
                    logger.warning(f"utg.json not found in {data_dir}")
                    return None
                
                # 记录加载开始时间
                load_start = time.time()
                
                # 使用UTG.load_utg加载UTG对象
                utg = UTG.load_utg(str(data_dir), keep_self_loops=True, logger=logger)
                
                load_duration = time.time() - load_start
                cls._cache_stats['loads'] += 1
                
                if utg is None:
                    logger.error(f"Failed to load UTG object for dataset '{dataset}'")
                    return None
                
                # 3. 存入缓存
                cache_entry = UTGCacheEntry(
                    utg_object=utg,
                    dataset=dataset,
                    load_time=time.time(),
                    last_access_time=time.time(),
                    access_count=1,
                    file_mtime=current_mtime
                )
                
                cls._cache[cache_key] = cache_entry
                logger.info(f"Loaded and cached UTG for dataset '{dataset}' in {load_duration:.2f}s")
                
                # 4. 执行缓存大小限制
                cls._enforce_cache_size_limit()
                
                return utg
                
            except Exception as e:
                logger.error(f"Error loading UTG object for dataset '{dataset}': {e}")
                return None
    
    @classmethod
    def _build_node_image_url(cls, dataset: str, image_path: str, utg_output_dir: Optional[str] = None) -> str:
        """将状态截图路径统一转换为前端可访问的 data/{dataset}/... URL。"""
        if not image_path:
            return ""

        normalized_path = str(image_path).replace("\\", "/")
        if normalized_path.startswith("data/"):
            return normalized_path

        if utg_output_dir:
            try:
                relative_path = os.path.relpath(image_path, utg_output_dir).replace("\\", "/")
                if not relative_path.startswith("../"):
                    normalized_path = relative_path
            except Exception:
                # 保持原路径继续兜底拼接
                pass

        return f"data/{dataset}/{normalized_path.lstrip('/')}"

    @classmethod
    async def get_utg(cls, dataset: str) -> Dict[str, Any]:
        """获取指定数据集的UTG数据

        Args:
            dataset: 数据集名称（由路由层从会话传入）

        Returns:
            UTG数据字典，包含nodes和edges
        """
        # 尝试加载UTG对象（使用缓存）
        utg = cls._load_utg_object(dataset)
        if utg is None:
            return {"nodes": [], "edges": []}
        
        try:
            # 使用UTG对象的to_dict方法获取数据
            utg_data = utg.to_dict()
            
            # 更新图片路径，包含数据集前缀
            for node in utg_data.get("nodes", []):
                if "image" in node:
                    node["image"] = cls._build_node_image_url(dataset, node["image"])
            
            return utg_data
        except Exception as e:
            logger.error(f"Error converting UTG to dict for dataset '{dataset}': {e}")
            return {"nodes": [], "edges": []}
    
    @classmethod
    async def update_event(cls, dataset: str, edge_id: str, old_event_str: str, event_type: str, event_str: str, new_from_state: Optional[str] = None, new_to_state: Optional[str] = None) -> Dict[str, Any]:
        """更新事件 - 支持状态改变

        Args:
            dataset: 数据集名称（由路由层从会话传入）
            edge_id: 边ID
            old_event_str: 旧事件字符串
            event_type: 事件类型
            event_str: 新事件字符串
            new_from_state: 新的源状态（可选）
            new_to_state: 新的目标状态（可选）
        """
        # 验证事件类型
        if not ValidationUtils.validate_event_type(event_type):
            raise ValueError(f"Invalid event type: {event_type}")

        # 获取UTG对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        # 使用锁保护UTG修改操作
        with utg_lock:
            try:
                # 解析边ID（格式：source_node-->target_node）
                if "-->" not in edge_id:
                    raise ValueError(f"Invalid edge ID format: {edge_id}")

                old_from_node, old_to_node = edge_id.split("-->", 1)

                # 确定新的源和目标状态
                new_from_node = new_from_state if new_from_state is not None else old_from_node
                new_to_node = new_to_state if new_to_state is not None else old_to_node

                # 获取状态对象
                old_from_state_obj = utg.get_state(old_from_node)
                old_to_state_obj = utg.get_state(old_to_node)
                new_from_state_obj = utg.get_state(new_from_node)
                new_to_state_obj = utg.get_state(new_to_node)

                if not all([old_from_state_obj, old_to_state_obj, new_from_state_obj, new_to_state_obj]):
                    raise ValueError("Failed to get state objects")

                # 使用UTG的update_transition方法，直接传入event_str，支持状态改变
                # update_transition 内部会自动处理字符串转换为 InputEvent
                success = utg.update_transition(
                    old_event_str, old_from_state_obj, old_to_state_obj,
                    event_str, new_from_state_obj, new_to_state_obj
                )

                if not success:
                    raise RuntimeError("Failed to update transition in UTG")

                # 更新缓存中的文件修改时间
                cls._update_cache_mtime(dataset)

                # 构建新的边ID
                new_edge_id = f"{new_from_node}-->{new_to_node}"
                state_changed = (old_from_node != new_from_node or old_to_node != new_to_node)

                return {
                    "message": "Event updated successfully",
                    "old_edge_id": edge_id,
                    "new_edge_id": new_edge_id,
                    "old_event_str": old_event_str,
                    "new_event_type": event_type,
                    "new_event_str": event_str,
                    "state_changed": state_changed
                }

            except Exception as e:
                logger.error(f"Error updating event: {e}")
                raise RuntimeError(f"Failed to update event: {e}")

    @classmethod
    async def delete_event(cls, dataset: str, edge_id: str, event_str: str) -> Dict[str, Any]:
        """删除边上的特定事件

        Args:
            dataset: 数据集名称（由路由层从会话传入）
            edge_id: 边ID
            event_str: 事件字符串
        """
        if not edge_id or not event_str:
            raise ValueError("Edge ID and event string are required")

        # 获取UTG对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        # 使用锁保护UTG修改操作
        with utg_lock:
            try:
                # 解析边ID
                if "-->" not in edge_id:
                    raise ValueError(f"Invalid edge ID format: {edge_id}")

                source_node, target_node = edge_id.split("-->", 1)

                # 获取状态对象
                from_state = utg.get_state(source_node)
                to_state = utg.get_state(target_node)

                if from_state is None or to_state is None:
                    raise ValueError("Failed to get state objects")

                # 使用UTG的remove_transition方法删除特定事件，直接传入event_str
                success = utg.remove_transition(event_str, from_state, to_state)

                if not success:
                    raise RuntimeError("Failed to remove event from UTG")

                # 更新缓存中的文件修改时间
                cls._update_cache_mtime(dataset)

                return {
                    "message": "Event deleted successfully",
                    "edge_id": edge_id,
                    "event_str": event_str
                }

            except Exception as e:
                logger.error(f"Error deleting event: {e}")
                raise RuntimeError(f"Failed to delete event: {e}")
    
    @classmethod
    async def delete_node(cls, dataset: str, node_id: str) -> NodeDelete:
        """删除节点及其相关边

        Args:
            dataset: 数据集名称（由路由层从会话传入）
            node_id: 节点ID
        """
        if not node_id:
            raise ValueError("Node ID is required")

        # 获取UTG对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        # 使用锁保护UTG修改操作
        with utg_lock:
            try:
                # 获取状态对象
                state = utg.get_state(node_id)
                if state is None:
                    raise ValueError(f"Node not found: {node_id}")

                # 使用UTG的remove_node方法
                success = utg.remove_node(state)

                if not success:
                    raise RuntimeError("Failed to remove node from UTG")

                # 更新缓存中的文件修改时间
                cls._update_cache_mtime(dataset)

                return NodeDelete(deleted_node_id=node_id)

            except Exception as e:
                logger.error(f"Error deleting node: {e}")
                raise RuntimeError(f"Failed to delete node: {e}")
    
    @classmethod
    async def create_event(cls, dataset: str, from_state: str, to_state: str, event_type: str, event_str: str) -> Dict[str, Any]:
        """创建新事件

        Args:
            dataset: 数据集名称（由路由层从会话传入）
            from_state: 源状态ID
            to_state: 目标状态ID
            event_type: 事件类型
            event_str: 事件字符串
        """
        # 验证事件类型
        if not ValidationUtils.validate_event_type(event_type):
            raise ValueError(f"Invalid event type: {event_type}")

        # 获取UTG对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        # 使用锁保护UTG修改操作
        with utg_lock:
            try:
                # 导入必要的类
                from droidbot.input_event import InputEvent

                # 获取状态对象（同时验证状态是否存在）
                from_state_obj = utg.get_state(from_state)
                to_state_obj = utg.get_state(to_state)

                if from_state_obj is None:
                    raise ValueError(f"Source node '{from_state}' does not exist")

                if to_state_obj is None:
                    raise ValueError(f"Target node '{to_state}' does not exist")

                # 创建事件对象
                event = InputEvent.from_event_str(event_str, from_state_obj)
                if event is None:
                    raise ValueError(f"Invalid event string: {event_str}")

                # 使用UTG的add_transition方法
                success = utg.add_transition(event, from_state_obj, to_state_obj)

                if not success:
                    raise RuntimeError("Failed to add transition to UTG")

                # 更新缓存中的文件修改时间
                cls._update_cache_mtime(dataset)

                # 生成边ID
                new_edge_id = f"{from_state}-->{to_state}"

                return {
                    "message": "Event created successfully",
                    "edge_id": new_edge_id,
                    "from": from_state,
                    "to": to_state,
                    "event_type": event_type,
                    "event_str": event_str
                }

            except Exception as e:
                logger.error(f"Error creating event: {e}")
                raise RuntimeError(f"Failed to create event: {e}")

    # ==================== 录制系统专用接口 ====================
    
    @classmethod
    def create_new_utg_sync(cls, dataset: str, device_info: Dict, app_info: Dict, output_dir: str) -> Dict[str, Any]:
        """创建并初始化新的UTG对象，供录制系统使用"""
        try:
            # 导入必要的类
            from droidbot.utg import UTG
            
            # 创建新的UTG对象
            utg = UTG(
                output_dir=output_dir,
                device_serial=device_info.get('serial', ''),
                device_model_number=device_info.get('model_number', ''),
                device_sdk_version=device_info.get('sdk_version', ''),
                app_signature=app_info.get('signature',''),
                app_package=app_info.get('package_name', ''),
                app_main_activity=app_info.get('main_activity', ''),
                app_num_total_activities=len(app_info.get('activities', [])),
                random_input=False,
                keep_self_loops=True  # 录制模式保留自循环
            )

            utg.save2dir()
            
            # 加载到缓存系统
            cache_key = cls._get_cache_key(dataset)
            current_mtime = cls._get_file_mtime(dataset)
            
            with cls._cache_lock:
                cache_entry = UTGCacheEntry(
                    utg_object=utg,
                    dataset=dataset,
                    load_time=time.time(),
                    last_access_time=time.time(),
                    access_count=1,
                    file_mtime=current_mtime
                )
                cls._cache[cache_key] = cache_entry
                cls._enforce_cache_size_limit()
            
            logger.info(f"Created and cached new UTG for dataset '{dataset}'")
            
            return {
                "message": "UTG created successfully",
                "dataset": dataset,
                "output_dir": output_dir,
                "utg_object_id": id(utg)
            }
            
        except Exception as e:
            logger.error(f"Error creating UTG for dataset '{dataset}': {e}")
            raise RuntimeError(f"Failed to create UTG: {e}")
    
    @classmethod
    def add_transition_sync(cls, event, from_state, to_state, dataset: str) -> Dict[str, Any]:
        """添加UTG状态转换，供RecordingWorkerThread使用

        Args:
            event: 事件对象
            from_state: 源状态对象
            to_state: 目标状态对象
            dataset: 数据集名称（必需，由录制系统传入）
        """
        # 获取UTG对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        # 使用锁保护UTG修改操作
        with utg_lock:
            try:
                # 使用UTG的add_transition方法
                success = utg.add_transition(event, from_state, to_state, skip_output=False)

                if not success:
                    logger.warning(f"UTG transition was not effective: {from_state.state_str} -> {to_state.state_str}")

                # 更新缓存中的文件修改时间
                cls._update_cache_mtime(dataset)

                return {
                    "success": success,
                    "from_state": from_state.state_str,
                    "to_state": to_state.state_str,
                    "event_str": event.get_event_str(from_state),
                    "event_type": getattr(event, 'event_type', 'unknown')
                }

            except Exception as e:
                logger.error(f"Error adding transition: {e}")
                raise RuntimeError(f"Failed to add transition: {e}")

    @classmethod
    def sync_state_node_sync(cls, state, dataset: str) -> Dict[str, Any]:
        """同步当前状态节点并输出 UTG，用于录制段首步持久化当前页面"""
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        with utg_lock:
            try:
                utg.add_node(state, skip_output=False)
                utg.save2dir()

                cls._update_cache_mtime(dataset)

                return {
                    "success": True,
                    "state": state.state_str
                }
            except Exception as e:
                logger.error(f"Error syncing state node: {e}")
                raise RuntimeError(f"Failed to sync state node: {e}")

    @classmethod
    async def get_branch_states(cls, dataset: str, node_id: str) -> Dict[str, Any]:
        """获取从指定节点开始的分支中的所有状态

        Args:
            dataset: 数据集名称（由路由层从会话传入）
            node_id: 目标节点ID

        Returns:
            包含分支状态列表的字典
        """
        if not node_id:
            raise ValueError("Node ID is required")

        # 加载UTG对象（使用缓存）
        utg = cls._load_utg_object(dataset)
        if utg is None:
            raise RuntimeError("Failed to load UTG data")

        try:
            # 检查节点是否存在
            if utg.get_state(node_id) is None:
                raise ValueError(f"Node '{node_id}' not found")

            # 使用UTG的find_branch_states方法查找分支状态
            branch_states_set = utg.find_branch_states(node_id)
            branch_states_list = list(branch_states_set)

            return {
                "node_id": node_id,
                "branch_states": branch_states_list,
                "count": len(branch_states_list)
            }

        except Exception as e:
            logger.error(f"Error getting branch states: {e}")
            raise RuntimeError(f"Failed to get branch states: {e}")

    @classmethod
    async def batch_delete_nodes(cls, dataset: str, node_ids: list) -> Dict[str, Any]:
        """批量删除节点

        Args:
            dataset: 数据集名称（由路由层从会话传入）
            node_ids: 要删除的节点ID列表

        Returns:
            删除结果的字典
        """
        if not node_ids:
            raise ValueError("Node IDs list is required")

        # 获取UTG对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        deleted_nodes = []
        failed_nodes = []

        # 使用锁保护UTG修改操作
        with utg_lock:
            try:
                # 逐个删除节点
                for node_id in node_ids:
                    try:
                        # 获取状态对象
                        state = utg.get_state(node_id)
                        if state is None:
                            failed_nodes.append({
                                "node_id": node_id,
                                "reason": "Node not found"
                            })
                            continue

                        # 使用UTG的remove_node方法，跳过单个节点的输出
                        success = utg.remove_node(state, skip_output=True)

                        if success:
                            deleted_nodes.append(node_id)
                        else:
                            failed_nodes.append({
                                "node_id": node_id,
                                "reason": "Failed to remove node from UTG"
                            })

                    except Exception as e:
                        logger.error(f"Error deleting node '{node_id}': {e}")
                        failed_nodes.append({
                            "node_id": node_id,
                            "reason": str(e)
                        })

                # 批量删除完成后，统一输出一次UTG
                if deleted_nodes:
                    utg.save2dir()
                    # 更新缓存中的文件修改时间
                    cls._update_cache_mtime(dataset)

                return {
                    "deleted_nodes": deleted_nodes,
                    "failed_nodes": failed_nodes
                }

            except Exception as e:
                logger.error(f"Error in batch delete nodes: {e}")
                raise RuntimeError(f"Failed to batch delete nodes: {e}")

    @classmethod
    async def set_first_state(cls, dataset: str, node_id: str) -> Dict[str, Any]:
        """设置节点为首状态

        Args:
            dataset: 数据集名称（由路由层从会话传入）
            node_id: 节点ID

        Returns:
            设置结果的字典
        """
        if not node_id:
            raise ValueError("Node ID is required")

        # 获取UTG对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        # 使用锁保护UTG修改操作
        with utg_lock:
            try:
                # 获取状态对象
                state = utg.get_state(node_id)
                if state is None:
                    raise ValueError(f"Node not found: {node_id}")

                # 使用UTG的set_first_state_str方法设置首状态
                success = utg.set_first_state(node_id)
                if not success:
                    raise RuntimeError("Failed to set first state")

                # 更新缓存中的文件修改时间
                cls._update_cache_mtime(dataset)

                return {
                    "message": "First state set successfully",
                    "node_id": node_id
                }

            except Exception as e:
                logger.error(f"Error setting first state: {e}")
                raise RuntimeError(f"Failed to set first state: {e}")

    @classmethod
    async def set_last_state(cls, dataset: str, node_id: str) -> Dict[str, Any]:
        """设置节点为末状态

        Args:
            dataset: 数据集名称（由路由层从会话传入）
            node_id: 节点ID

        Returns:
            设置结果的字典
        """
        if not node_id:
            raise ValueError("Node ID is required")

        # 获取UTG对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        # 使用锁保护UTG修改操作
        with utg_lock:
            try:
                # 获取状态对象
                state = utg.get_state(node_id)
                if state is None:
                    raise ValueError(f"Node not found: {node_id}")

                success = utg.set_last_state(state)
                if not success:
                    raise RuntimeError("Failed to set last state")

                # 更新缓存中的文件修改时间
                cls._update_cache_mtime(dataset)

                return {
                    "message": "Last state set successfully",
                    "node_id": node_id
                }

            except Exception as e:
                logger.error(f"Error setting last state: {e}")
                raise RuntimeError(f"Failed to set last state: {e}")

    @classmethod
    async def set_node_labels(
        cls,
        dataset: str,
        node_id: str,
        labels: list,
        label_meta: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """设置节点的自定义标签列表

        Args:
            dataset: 数据集名称（由路由层从会话传入）
            node_id: 节点ID
            labels: 标签列表

        Returns:
            设置结果的字典
        """
        if not node_id:
            raise ValueError("Node ID is required")

        if not isinstance(labels, list):
            raise ValueError("Labels must be a list")
        if label_meta is not None and not isinstance(label_meta, dict):
            raise ValueError("label_meta must be a dict")

        # 获取UTG对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        # 使用锁保护UTG修改操作
        with utg_lock:
            try:
                # 获取状态对象
                state = utg.get_state(node_id)
                if state is None:
                    raise ValueError(f"Node not found: {node_id}")

                # 使用UTG的set_label方法设置自定义标签
                success = utg.set_label(node_id, labels)
                if not success:
                    raise RuntimeError("Failed to set labels")
                
                if label_meta is not None:
                    meta_success = utg.set_label_meta(node_id, label_meta)
                    if not meta_success:
                        raise RuntimeError("Failed to set label meta")

                # 保存UTG
                utg.save2dir()

                # 更新缓存中的文件修改时间
                cls._update_cache_mtime(dataset)

                return {
                    "message": "Labels set successfully",
                    "node_id": node_id,
                    "labels": labels,
                    "label_meta": label_meta
                }

            except Exception as e:
                logger.error(f"Error setting node labels: {e}")
                raise RuntimeError(f"Failed to set node labels: {e}")

    @classmethod
    async def batch_restore_nodes(cls, dataset: str, state_strs: list) -> Dict[str, Any]:
        """批量恢复节点"""

        if not state_strs:
            raise ValueError("state_strs list is required")

        # 获取 UTG 对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")

        restored_nodes = []
        failed_nodes = []

        # 使用锁保护整个恢复过程
        with utg_lock:
            try:
                for state_str in state_strs:
                    try:
                        success = utg.restore_node(state_str, skip_output=True)

                        if success:
                            restored_nodes.append(state_str)
                        else:
                            failed_nodes.append({
                                "state_str": state_str,
                                "reason": "Failed to restore node"
                            })

                    except Exception as e:
                        logger.error(f"Error restoring node '{state_str}': {e}")
                        failed_nodes.append({
                            "state_str": state_str,
                            "reason": str(e)
                        })

                # 批量恢复完成，统一写UTG
                if restored_nodes:
                    utg.save2dir()
                    cls._update_cache_mtime(dataset)

                return {
                    "restored_nodes": restored_nodes,
                    "failed_nodes": failed_nodes
                }

            except Exception as e:
                logger.error(f"Error in batch restore nodes: {e}")
                raise RuntimeError(f"Failed to batch restore nodes: {e}")
            
    @classmethod        
    async def get_deleted_nodes(cls, dataset: str):
        """获取删除节点"""

        # 获取 UTG 对象和锁
        utg, utg_lock = cls._get_utg_with_lock(dataset)
        if utg is None or utg_lock is None:
            raise RuntimeError("Failed to load UTG data")
        
        with utg_lock:
            try:
                # 获取被删除的state对象列表
                deleted_states = utg.get_deleted_states()

                # 组装被删除节点信息列表
                deleted_nodes = [
                    {
                        "state_str": state.state_str,
                        "image": cls._build_node_image_url(
                            dataset=dataset,
                            image_path=state.screenshot_path,
                            utg_output_dir=getattr(utg, "output_dir", None)
                        )
                    }
                    for state in deleted_states if state and state.screenshot_path
                ]
            
                return deleted_nodes

            except Exception as e:
                logger.error(f"Error in get deleted nodes: {e}")
                raise RuntimeError(f"Failed to get deleted nodes: {e}")
