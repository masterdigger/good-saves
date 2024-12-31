from loguru import logger

def setup_logger():
    """Setup and configure loguru logger."""
    logger.remove()
    
    log_format = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    log_rotation = "10 MB"
    log_retention = "10 days"
    
    logger.add("logs/debug.log", 
               format=log_format,
               level="DEBUG", 
               rotation=log_rotation, 
               retention=log_retention)
    logger.add("logs/error.log", 
               format=log_format,
               level="ERROR", 
               rotation=log_rotation, 
               retention=log_retention)
    logger.add("logs/info.log", 
               format=log_format,
               level="INFO", 
               rotation=log_rotation, 
               retention=log_retention)
    logger.info("Logger initialized.")
    return logger
