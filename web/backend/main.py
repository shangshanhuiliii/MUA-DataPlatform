import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Config
from .errors import AppError
from .routers import auth, batches, batch_allocations, cloud_devices, recordings, task_record, tasks, users, utg, workspaces

# 配置日志（从环境变量读取级别）
logging.basicConfig(
    level=Config.get_log_level(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 启动前校验路径配置，统一 directory_name 必须相对 DATA_DIR
Config.validate_paths()

# 确保必要的目录存在
Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
Config.RECORD_DIR.mkdir(parents=True, exist_ok=True)

# 创建FastAPI应用实例
# 生产环境禁用文档端点
app = FastAPI(
    title="DroidBot UTG Server",
    version="2.0.0",
    description="Modular DroidBot Web Interface API",
    docs_url="/docs" if Config.DEBUG else None,
    redoc_url="/redoc" if Config.DEBUG else None,
    openapi_url="/openapi.json" if Config.DEBUG else None,
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(utg.router)
app.include_router(task_record.router)
app.include_router(tasks.router)
app.include_router(batches.router)
app.include_router(batch_allocations.router)
app.include_router(recordings.router)
app.include_router(cloud_devices.router)
app.include_router(workspaces.router)

# 挂载静态文件目录 (follow_symlink=True 支持软链接)
app.mount("/data", StaticFiles(directory=str(Config.DATA_DIR), follow_symlink=True), name="data")

# 挂载 /record 路径，支持前端直接使用 /record/xxx 访问录制数据
app.mount("/record", StaticFiles(directory=str(Config.RECORD_DIR), follow_symlink=True), name="record")

# 新的静态文件路径
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_frontend():
    """服务前端页面"""
    # Try to serve the new template first, fallback to old one for compatibility
    from pathlib import Path
    
    new_template = Path("templates/index.html")
    old_template = Path("index.html")
    
    if new_template.exists():
        return FileResponse("templates/index.html")
    elif old_template.exists():
        return FileResponse("index.html")
    else:
        return {"error": "Frontend template not found"}

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "service": "DroidBot UTG Server"
    }

@app.get("/api/health")
async def api_health_check():
    """API健康检查"""
    from .services.task_record_service import task_record_service

    try:
        # 检查 TaskRecord 服务状态
        task_record_sessions = await task_record_service.get_active_sessions()

        return {
            "status": "healthy",
            "api_version": "2.0.0",
            "taskrecord_sessions_count": len(task_record_sessions)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# 异常处理
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    _ = request
    return exc.to_response()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    _ = request
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    _ = request, exc  # 标记参数为已使用，避免警告
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "detail": "The requested resource was not found"}
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    _ = request, exc  # 标记参数为已使用，避免警告
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": "An unexpected error occurred"}
    )

# 启动时的初始化
@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    logger = logging.getLogger(__name__)
    logger.info("Starting DroidBot UTG Server v2.0.0")

    # 检查数据目录
    data_dir = Config.DATA_DIR
    if not data_dir.exists():
        logger.warning(f"Data directory does not exist: {data_dir}")
    else:
        logger.info(f"Data directory found: {data_dir}")

    logger.info("🧵 Initializing YOLO Inference Engine & Model Manager...")
    try:
        from droidbot.adapter.yolo_model_manager import YOLOModelManager
        
        yolo_cfg = Config.get_yolo_config()
        YOLOModelManager.configure(**yolo_cfg)
        YOLOModelManager()
        
        logger.info("🚀 YOLO initialized with following settings:")
        for key, value in yolo_cfg.items():
            logger.info(f"   - {key}: {value}")
    except Exception as e:
        logger.error(f"❌ YOLO configuration failed: {e}")

    # 初始化 TaskRecord 服务组件
    logger.info("🧵 Initializing Thread+Queue components for TaskRecordService")
    try:
        from .services.task_record_service import task_record_service
        logger.info("✅ TaskRecordService initialized successfully")
        logger.info("ℹ️  Using Thread+Queue architecture for recording")
        
        # 显示服务配置状态
        if task_record_service.is_threaded_recording_enabled():
            logger.info("🔧 Threaded recording mode: ENABLED")
        else:
            logger.info("🔧 Threaded recording mode: DISABLED (legacy compatibility)")
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize TaskRecordService: {e}")
        logger.info("⚠️  Service may not function properly")

    # 启动 session 清理任务
    logger.info("🔄 Starting session cleanup task")
    try:
        from .session_config import schedule_session_cleanup, SESSION_CLEANUP_INTERVAL, SESSION_IDLE_TIMEOUT

        schedule_session_cleanup(
            interval_seconds=SESSION_CLEANUP_INTERVAL,
            timeout_seconds=SESSION_IDLE_TIMEOUT
        )
        logger.info(f"✅ Session cleanup task started (interval: {SESSION_CLEANUP_INTERVAL}s, idle_timeout: {SESSION_IDLE_TIMEOUT}s)")
    except Exception as e:
        logger.error(f"❌ Failed to start session cleanup task: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理"""
    logger = logging.getLogger(__name__)
    logger.info("Shutting down DroidBot UTG Server")

    # 停止 session 清理任务
    logger.info("🔄 Stopping session cleanup task")
    try:
        from .session_config import stop_session_cleanup_task
        await stop_session_cleanup_task()
        logger.info("✅ Session cleanup task stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping session cleanup task: {e}")

    # 清理 TaskRecord 服务组件
    logger.info("🧵 Cleaning up Thread+Queue components...")
    try:
        from .services.task_record_service import task_record_service

        # 清理死亡会话
        cleaned_count = await task_record_service.cleanup_dead_sessions()
        logger.info(f"✅ Cleaned up {cleaned_count} thread-based sessions")

        # 获取活跃会话数量用于日志
        active_sessions = await task_record_service.get_active_sessions()
        if active_sessions:
            logger.warning(f"⚠️  {len(active_sessions)} active sessions still running during shutdown")

        logger.info("🏁 Thread+Queue architecture cleanup complete")
    except Exception as e:
        logger.error(f"❌ Error during Thread+Queue cleanup: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=Config.HOST, 
        port=Config.PORT,
        log_level="info"
    )
