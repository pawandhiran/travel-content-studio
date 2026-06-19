import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

LOG_DIR = Path.home() / ".travel-content-studio" / "logs"
JOBS_LOG_DIR = LOG_DIR / "jobs"
APP_LOG_FILE = LOG_DIR / "app.log"


def _ensure_log_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog with console output for dev, JSON for production.

    Also sets up a rotating file handler for the main application log at
    ~/.travel-content-studio/logs/app.log.
    """
    _ensure_log_dirs()
    log_level = log_level.upper()
    is_dev = True

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_dev:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[*shared_processors, renderer],
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)

    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s -- %(message)s"
    )
    file_handler = RotatingFileHandler(
        APP_LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(file_formatter)

    root = logging.getLogger()
    root.handlers = [console_handler, file_handler]
    root.setLevel(getattr(logging, log_level, logging.INFO))


def get_job_logger(job_id: str) -> logging.Logger:
    """Create a dedicated file logger for a specific job.

    Writes to ~/.travel-content-studio/logs/jobs/{job_id}.log.
    """
    _ensure_log_dirs()
    job_log_file = JOBS_LOG_DIR / f"{job_id}.log"

    job_logger = logging.getLogger(f"job.{job_id}")
    job_logger.setLevel(logging.DEBUG)
    job_logger.handlers = []
    job_logger.propagate = False

    fh = logging.FileHandler(job_log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    job_logger.addHandler(fh)

    return job_logger


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structlog instance."""
    return structlog.get_logger(name)
