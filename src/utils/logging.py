"""Centralized logging setup for chain_gambler.

Configures loguru with consistent formatting and file rotation.
"""
import sys
from loguru import logger

from src.utils.paths import LOGS_DIR


def setup_logging(level: str = "INFO", log_to_file: bool = True):
    """Configure loguru logging for the project.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_to_file: Whether to also log to files
    """
    # Remove default handler
    logger.remove()

    # Console handler — compact format
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    if log_to_file:
        import os
        os.makedirs(LOGS_DIR, exist_ok=True)

        # Main log file — rotates at 10MB, keeps 5
        logger.add(
            os.path.join(LOGS_DIR, "chain_gambler.log"),
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation="10 MB",
            retention=5,
            compression="gz",
        )

        # Error-only log
        logger.add(
            os.path.join(LOGS_DIR, "errors.log"),
            level="ERROR",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation="10 MB",
            retention=10,
            compression="gz",
        )

    logger.info(f"Logging initialized (level={level}, file={log_to_file})")