import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8100,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
