import sys
from loguru import logger

def setup_logger():
    """Set up the logger with multiple outputs for comprehensive logging."""

    # Remove default logger configuration
    logger.remove()

    # Log to a text file for general application logs
    logger.add(
        "logs/app.log",
        rotation="500 MB",
        level="DEBUG",  # General logging for information and higher levels
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}"
    )

    # Log to a JSON file for structured and detailed logging
    logger.add(
        "logs/app.json",
        rotation="500 MB",
        level="DEBUG",  # Debug-level logging for detailed tracing
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}",
        serialize=True  # JSON format for easy parsing
    )

    # Console logging for real-time debugging during development
    logger.add(
        sys.stderr,
        level="DEBUG",  # Show debug information in the console
        format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level}</level> | <cyan>{message}</cyan>",
        colorize=True  # Colorize console logs for better visibility
    )

    logger.add(
        "logs/script.log",
        rotation="10 MB",
        retention="10 days",
        level="DEBUG"
    )

    return logger