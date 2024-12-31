import json
import random
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
import lxml
from loguru import logger
from pydantic import BaseModel, ValidationError
from config.logger_config import setup_logger
from http_client import HTTPClient
from form_handler import FormHandler
from cookie_handler import CookieHandler
from config import get_base_response  # P0280

# Setup logging
logger = setup_logger()

# Directory path
LOGS_DIR = Path("logs")

# File paths
CONFIG_FILE = Path("config/config.json")
RECENT_HEADERS_FILE = Path("recent_headers.json")
RESPONSE_HTML_FILE = LOGS_DIR / "response_html.html"
POST_RESPONSE_HTML_FILE = LOGS_DIR / "post_response_xnl.xml"


@lru_cache(maxsize=None)
def load_config() -> Tuple[str, str, str, Dict[str, List[str]], List[Dict[str, str]], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Load configuration from config.json and parse URL."""
    with open(CONFIG_FILE, "r") as config_file:
        config = json.load(config_file)

    parsed_url = urlparse(config["url"])
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    path = parsed_url.path
    host = parsed_url.netloc
    query_params = parse_qs(parsed_url.query)

    # Dynamiskt val av ett `base_response`
    if "base_responses" in config and config["base_responses"]:
        base_response = random.choice(config["base_responses"])
        logger.debug(f"Selected dynamic base_response: {base_response}")
    else:
        base_response = {}
        logger.warning("No base_responses found in config.json, using empty response.")

    test_mode = config.get("test_mode", False)
    logger.debug("Loaded configuration successfully.")
    return base_url, path, host, query_params, config["headers_list"], config["data_params"], base_response, config["form_post_url"], test_mode


BASE_URL, PATH, HOST, QUERY_PARAMS, HEADERS_LIST, DATA_PARAMS, BASE_RESPONSE, FORM_POST_URL, TEST_MODE = load_config()
POST_URL = None


class FormData(BaseModel):
    """Model to represent and validate form data."""
    data: Dict[str, Any]


if __name__ == "__main__":
    logger.info("Starting application.")

    try:
        with HTTPClient(base_url=BASE_URL, headers_list=HEADERS_LIST) as client:
            logger.info("HTTPClient initialized successfully.")

            response = client.get(PATH, params=QUERY_PARAMS)
            logger.info("Initial GET request successful.")

            soup = BeautifulSoup(response.text, "html.parser")
            form_handler = FormHandler(client=client, form_data=FormData(data={}), path=PATH, query_params=QUERY_PARAMS, base_response=BASE_RESPONSE)  # Pdb80

            form_handler.parse_cookie(soup)
            logger.info("Cookies parsed and set.")

            post_response = form_handler.submit_form()
            if post_response:
                logger.info(f"Form submitted successfully. Response: {post_response.text[:100]}...")
            else:
                logger.warning("No response received after form submission.")

    except Exception as e:
        logger.critical(f"Application terminated due to an error: {e}")
