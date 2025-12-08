"""
Centralized logging configuration for the LLM Gamer Agent.
"""
import logging
import sys
from typing import Optional


def setup_logger(
    name: str = "llmgamer",
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Setup and return a configured logger.
    
    Args:
        name: Logger name (usually __name__ of the module)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
    
    Returns:
        Configured logging.Logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid adding multiple handlers if already configured
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File Handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.
    Uses the root 'llmgamer' logger as parent for consistent formatting.
    
    Args:
        name: Module name (typically __name__)
    
    Returns:
        logging.Logger instance
    """
    # Ensure the root logger is configured
    root_logger = logging.getLogger("llmgamer")
    if not root_logger.handlers:
        setup_logger()
    
    return logging.getLogger(f"llmgamer.{name}")
