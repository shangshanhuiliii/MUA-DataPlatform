import logging
import threading
import queue
import time
import cv2
import numpy as np
from pathlib import Path
from concurrent.futures import Future, TimeoutError
from typing import Any, Optional, Dict, List
from dataclasses import dataclass
from collections import deque
import onnxruntime as ort

_STOP = object()  # 唯一sentinel

@dataclass
class _InferenceTask:
    image: Any
    params: Dict
    future: Future
    enqueue_time: float

class MockYOResults:
    """模拟Ultralytics的Results对象，"""
    class SingleBox:
        def __init__(self, data_row):
            self.xyxy = np.array(data_row[:4]).reshape(1, 4)
            self.conf = data_row[4]
            self.cls = data_row[5]

    class MockBoxes:
        def __init__(self, data):
            self.data = data
            
        def __len__(self):
            return len(self.data)

        def __getitem__(self, index):
            if isinstance(index, slice):
                return [MockYOResults.SingleBox(row) for row in self.data[index]]
            return MockYOResults.SingleBox(self.data[index])

    def __init__(self, boxes_data):
        self.boxes = self.MockBoxes(boxes_data)


class YOLOModelManager:
    """
    YOLO ONNX 异步多线程推理管理器
    """
    _instance = None
    _config = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._instance_lock:
            if cls._instance is None:
                # 增如果没有手动 configure，给一个默认配置
                if cls._config is None:
                    logging.getLogger(cls.__name__).warning("YOLOModelManager not configured explicitly. Using default configurations.")
                    cls.configure() 
                
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
   
    @classmethod
    def configure(
        cls,
        *,
        device: str = "cpu",          
        max_queue_size: int = 64,
        num_threads: int = 1 ,
        inference_timeout: float = 30.0,
        yolo_model_path: Optional[str] = None,
        onnx_imgsz: int = 640,
        onnx_conf: float = 0.2,
        onnx_iou: float = 0.7,
    ):
        # ===== 参数合法性校验 =====
        if max_queue_size <= 0:
            raise ValueError(f"max_queue_size must be > 0, got {max_queue_size}")

        if num_threads <= 0:
            raise ValueError(f"num_threads must be > 0, got {num_threads}")

        if inference_timeout <= 0:
            raise ValueError(f"inference_timeout must be > 0, got {inference_timeout}")

        if onnx_imgsz <= 0:
            raise ValueError(f"onnx_imgsz must be > 0, got {onnx_imgsz}")

        if not (0.0 <= onnx_conf <= 1.0):
            raise ValueError(f"onnx_conf must be in [0,1], got {onnx_conf}")

        if not (0.0 <= onnx_iou <= 1.0):
            raise ValueError(f"onnx_iou must be in [0,1], got {onnx_iou}")

        if device not in ("cpu", "cuda","gpu"):
            raise ValueError(f"device must be 'cpu' or 'cuda' or 'gpu', got {device}")
        
        with cls._instance_lock:
            cls._config = {
                "device": device,
                "max_queue_size": max_queue_size,
                "inference_timeout": inference_timeout,
                "yolo_model_path": yolo_model_path,
                "onnx_imgsz": onnx_imgsz,
                "onnx_conf": onnx_conf,
                "onnx_iou": onnx_iou,
                "num_threads": num_threads
            }

    def __init__(self):
        with self.__class__._instance_lock:
            if getattr(self, "_initialized", False):
                return

        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.device = self._config["device"]
        self.logger.info(f"YOLOModelManager (ONNX) initialized. Target device: {self.device}")

        self.__inference_config = dict(
            imgsz=self._config["onnx_imgsz"],
            conf=self._config["onnx_conf"],
            iou=self._config["onnx_iou"]
        )

        self.max_queue_size = self._config["max_queue_size"]
        self._timeout = self._config["inference_timeout"]
        self._model_path = self._config["yolo_model_path"]
        self.num_threads = self._config["num_threads"]

        self._session: Optional[ort.InferenceSession] = None
        self._input_name: str = ""
        self._model_lock = threading.Lock() # 用于保护模型加载阶段
        self._is_shutdown = False

        self._metrics_lock = threading.Lock()
        self._total = 0
        self._failed = 0
        self._latencies = deque(maxlen=1000)

        self._queue = queue.Queue(maxsize=self.max_queue_size)
        self._workers: List[threading.Thread] = []
        
        # 启动多个Worker线程去争抢同一个Queue
        for i in range(self.num_threads):
            worker = threading.Thread(
                target=self._worker_loop, 
                name=f"ONNX-Inference-Worker-{i}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)
        self._find_model_path()  # 预先验证模型路径，避免Worker线程中重复验证
        self._initialized = True

    # ONNX 初始化与预处理
    def _load_model_once(self):
        if self._session is not None:
            return

        with self._model_lock:
            if self._session is not None:
                return
            model_path = self._find_model_path()
            
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            
            # 如果启用了多线程 Worker (并发数 > 1)，限制单个算子的计算线程，防止CPU过载
            if self.device == "cpu":
                sess_options.intra_op_num_threads = max(1, 8 // self.num_threads) 
                providers = ['CPUExecutionProvider']
            else:
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']

            self._session = ort.InferenceSession(str(model_path), sess_options=sess_options, providers=providers)
            self._input_name = self._session.get_inputs()[0].name

    def _find_model_path(self) -> Path:
        if self._model_path and str(self._model_path).strip().upper() == "NONE":
            self._model_path = None
        if self._model_path:
            p = Path(self._model_path).resolve()
            if not p.exists():
                raise FileNotFoundError(f"Specified YOLO model not found: {p}")
            if p.suffix != ".onnx":
                raise ValueError(f"Model must be a .onnx file, got: {p}")
            self.logger.info(f"📍 YOLO model path: {p}")
            return p

        base_dir = Path(__file__).resolve().parents[1] / "resources" / "yolo"

        if not base_dir.is_dir():
            raise FileNotFoundError(f"YOLO resources directory not found at: {base_dir}")

        onnx_files = list(base_dir.glob("*.onnx"))

        if not onnx_files:
            raise FileNotFoundError(f"No .onnx models found in {base_dir}")

        target_model = max(onnx_files, key=lambda p: p.stat().st_mtime)
        self.logger.info(f"📍 YOLO model path: {target_model} ")

        return target_model

    def _preprocess(self, img: np.ndarray, imgsz: int):
        """Letterbox预处理对齐"""
        shape = img.shape[:2]
        r = min(imgsz / shape[0], imgsz / shape[1])
        new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
        dw, dh = (imgsz - new_unpad[0]) / 2, (imgsz - new_unpad[1]) / 2
        
        if shape[::-1] != new_unpad:
            img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
            
        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
        
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = img.transpose(2, 0, 1)
        img = np.expand_dims(img, axis=0) # BCHW
        
        return img, (r, r), (left, top), shape

    def _postprocess(self, outputs, ratio, pad, orig_shape, conf_thres, iou_thres):
        """
        NMS与坐标还原
        """
        preds = np.squeeze(outputs[0]).T  
        
        boxes_cxcywh = preds[:, :4]
        class_scores = preds[:, 4:]
        
        scores = np.max(class_scores, axis=1)
        class_ids = np.argmax(class_scores, axis=1)
        
        mask = scores > conf_thres
        boxes_cxcywh = boxes_cxcywh[mask]
        scores = scores[mask]
        class_ids = class_ids[mask]
        
        if len(boxes_cxcywh) == 0:
            return np.array([])

        r_w, r_h = ratio
        pad_w, pad_h = pad
        
        boxes_cxcywh[:, 2] /= r_w
        boxes_cxcywh[:, 3] /= r_h
        boxes_cxcywh[:, 0] = (boxes_cxcywh[:, 0] - pad_w) / r_w
        boxes_cxcywh[:, 1] = (boxes_cxcywh[:, 1] - pad_h) / r_h
        
        x1y1x2y2 = np.copy(boxes_cxcywh)
        x1y1x2y2[:, 0] = boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] / 2
        x1y1x2y2[:, 1] = boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] / 2
        x1y1x2y2[:, 2] = boxes_cxcywh[:, 0] + boxes_cxcywh[:, 2] / 2
        x1y1x2y2[:, 3] = boxes_cxcywh[:, 1] + boxes_cxcywh[:, 3] / 2

        # 设置一个极大的偏移量，确保不同类别的框在虚拟空间中互不重叠
        max_coordinate = 7680 
        offsets = class_ids * max_coordinate
        
        boxes_for_nms = np.zeros_like(boxes_cxcywh)
        boxes_for_nms[:, 0] = x1y1x2y2[:, 0] + offsets  # x_min + 偏移
        boxes_for_nms[:, 1] = x1y1x2y2[:, 1] + offsets  # y_min + 偏移
        boxes_for_nms[:, 2] = boxes_cxcywh[:, 2]        # width
        boxes_for_nms[:, 3] = boxes_cxcywh[:, 3]        # height

        indices = cv2.dnn.NMSBoxes(
            boxes_for_nms.tolist(), 
            scores.tolist(), 
            conf_thres, 
            iou_thres
        )
        if len(indices) == 0:
            return np.array([]) 
        indices = indices.flatten()
        
        final_boxes = x1y1x2y2[indices]
        final_scores = scores[indices]
        final_class_ids = class_ids[indices]
        results = np.column_stack((final_boxes, final_scores, final_class_ids))
        
        return results

    # Worker 调度逻辑
    def _worker_loop(self):
        while True:
            task = self._queue.get()
            
            if task is _STOP:
                self._queue.task_done()
                break

            if time.time() - task.enqueue_time > self._timeout:
                task.future.set_exception(TimeoutError("Task expired in queue"))
                self._record_metrics(0, ok=False)
                self._queue.task_done()
                continue

            start_infer_time = time.time()
            try:
                self._load_model_once()
                
                imgsz = task.params.get("imgsz", 640)
                conf = task.params.get("conf", 0.25)
                iou = task.params.get("iou", 0.45)
                
                raw_img = cv2.imread(task.image) if isinstance(task.image, str) else task.image
                if raw_img is None:
                    raise ValueError(f"Failed to read image or image is empty. Input: {task.image}")
                img_in, ratio, pad, orig_shape = self._preprocess(raw_img, imgsz)
                # 推理
                outputs = self._session.run(None, {self._input_name: img_in})
                # 处理与格式兼容
                boxes_data = self._postprocess(outputs, ratio, pad, orig_shape, conf, iou)
                mock_result = [MockYOResults(boxes_data)] # 包装成列表，对齐原版
                
                task.future.set_result(mock_result)
                
                latency = time.time() - start_infer_time
                self._record_metrics(latency, ok=True)
                
            except Exception as e:
                self.logger.error(f"Inference error: {str(e)}", exc_info=True)
                task.future.set_exception(e)
                self._record_metrics(0, ok=False)
            finally:
                self._queue.task_done()

    def _record_metrics(self, latency: float, ok: bool):
        with self._metrics_lock:
            self._total += 1
            if not ok: self._failed += 1
            if latency > 0: self._latencies.append(latency)
     
    # 对外 API
    def predict(self, image: Any, **override) -> Any:
        future = self.predict_async(image, **override)
        client_wait_timeout = self._timeout + 2.0 
        return future.result(timeout=client_wait_timeout)

    def predict_async(self, image: Any, **override) -> Future:
        future = Future()
        if self._is_shutdown:
            future.set_exception(RuntimeError("YOLOModelManager is shut down."))
            return future

        params = {**self.__inference_config, **override}
        task = _InferenceTask(image, params, future, time.time())

        try:
            self._queue.put(task, timeout=2.0)
        except queue.Full:
            self.logger.warning("Inference queue is full, dropping request.")
            future.set_exception(queue.Full("Inference queue is full. Try again later."))

        return future

    def shutdown(self):
        if self._is_shutdown: return
        self.logger.info("Shutting down YOLOModelManager...")
        self._is_shutdown = True

        try:
            for _ in self._workers:
                try: self._queue.put(_STOP, timeout=1.0)
                except queue.Full: break
            
            for worker in self._workers:
                if worker.is_alive():
                    worker.join(timeout=3.0)
        finally:
            if self._session:
                del self._session
                self._session = None

    def get_metrics(self) -> Dict[str, Any]:
        with self._metrics_lock:
            avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
            return {
                "total_requests": self._total,
                "failed_requests": self._failed,
                "avg_latency_sec": round(avg_latency, 4),
                "queue_size": self._queue.qsize()
            }