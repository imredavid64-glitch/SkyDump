import os
import logging
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

# Get the backend directory (where .env is located)
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(BACKEND_DIR, ".env")


class Settings(BaseSettings):
    APP_NAME: str = "SkyDump AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api"
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/skydump"
    
    # STAC API
    STAC_API_URL: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    SENTINEL2_COLLECTION: str = "sentinel-2-l2a"
    MAX_CLOUD_COVER: int = 20
    
    # Anomaly detection thresholds
    NDVI_DELTA_THRESHOLD: float = -0.35
    SWIR_THRESHOLD: float = 0.25
    MIN_CONTOUR_AREA: float = 10000.0  # m^2
    
    # Risk scoring weights
    AREA_WEIGHT: float = 0.4
    CONFIDENCE_WEIGHT: float = 0.3
    PROXIMITY_WEIGHT: float = 0.3
    
    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "https://skydump.vercel.app"]
    EXTRA_ALLOWED_ORIGINS: str = ""
    
    # JWT
    JWT_SECRET: str = "your-super-secret-jwt-key-change-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Sentry
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # seconds
    
    # Email (for alerts)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "alerts@skydump.ai"
    
    # Webhook
    DISCORD_WEBHOOK_URL: str = ""
    SLACK_WEBHOOK_URL: str = ""
    
    # Export
    EXPORT_DIR: str = "./exports"
    
    model_config = ConfigDict(
        env_file=ENV_FILE,
        case_sensitive=True,
        extra='allow'  # Allow extra fields from .env
    )

    @property
    def all_allowed_origins(self) -> list[str]:
        origins = self.ALLOWED_ORIGINS.copy()
        if self.EXTRA_ALLOWED_ORIGINS:
            origins.extend([o.strip() for o in self.EXTRA_ALLOWED_ORIGINS.split(",") if o.strip()])
        return origins


settings = Settings()

# Configure structured logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        import json
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


def setup_logging():
    if settings.DEBUG:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root_logger = logging.getLogger()
        root_logger.handlers = [handler]
        root_logger.setLevel(logging.INFO)
    
    # Reduce noise from third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)