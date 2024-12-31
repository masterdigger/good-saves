from loguru import logger

def setup_logger():
    """Setup and configure loguru logger."""
    logger.remove()
    logger.add("logs/debug.log", 
               format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
               level="DEBUG", 
               rotation="10 MB", 
               retention="10 days")
    logger.add("logs/error.log", 
               format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
               level="ERROR", 
               rotation="10 MB", 
               retention="10 days")
    logger.info("Logger initialized.")
    return logger