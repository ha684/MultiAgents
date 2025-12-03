# src/utils/logger_conf.py
import os

from loguru import logger

from .stdout_wrapper import SAFE_STDOUT

logs_dir = "logs"
os.makedirs(logs_dir, exist_ok=True)

logger.remove()

logger.add(
    SAFE_STDOUT,
    format="<g>{time:MM-DD HH:mm:ss}</g> |<lvl>{level:^8}</lvl>| {file}:{line} | {message}",
    backtrace=True,
    diagnose=True,
)

logger.add(
    os.path.join(logs_dir, "app_{time:YYYY-MM-DD}.log"),
    format="{time:YYYY-MM-DD HH:mm:ss} |{level:^8}| {file}:{line} | {message}",
    rotation="00:00",
    retention="30 days",
    compression="zip",
    backtrace=True,
    diagnose=True,
    level="DEBUG",
)
