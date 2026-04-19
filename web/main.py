# DroidBot Web Interface v2.0
# This file maintains backward compatibility while using the new modular backend

# 必须在导入 backend 模块之前加载 .env，否则 Config 类属性会在 load_dotenv 之前被求值
from dotenv import load_dotenv
load_dotenv(override=True)

from backend.main import app

print()

# Re-export the app for backward compatibility
__all__ = ['app']

if __name__ == "__main__":
    import uvicorn
    from backend.config import Config
    
    print("Starting DroidBot UTG Server v2.0.0...")
    print(f"Server will be available at: http://{Config.HOST}:{Config.PORT}")
    print("Press Ctrl+C to stop the server")
    
    uvicorn.run(
        app, 
        host=Config.HOST, 
        port=Config.PORT,
        log_level="info"
    )