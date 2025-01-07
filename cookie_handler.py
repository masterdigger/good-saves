import re

from bs4 import BeautifulSoup
from http_client import HTTPClient
from loguru import logger


class CookieHandler:
    """Handles parsing and setting cookies from HTML."""

    def __init__(self, client: HTTPClient, host: str):
        self.client = client
        self.host = host

    def parse_and_set_cookies(self, soup: BeautifulSoup):
        """Extract and set cookies from JavaScript in the response."""
        try:
            script_tag = soup.find(string=re.compile("Helper.setCookie"))
            if script_tag:
                logger.info("JavaScript containing cookies found.")
                pattern = r'Helper\.setCookie\("([^"]+)",\s*"([^"]+)",\s*(true|false)\)'
                match = re.search(pattern, script_tag)
                if match:
                    cookie_name, cookie_value, _ = match.groups()
                    self.client.new_cookie(
                        (cookie_name, cookie_value), domain=self.host, path="/"
                    )
                    logger.info(f"New cookie set: {cookie_name}")
                else:
                    logger.warning("No matching cookie pattern found in script tag.")
            else:
                logger.warning("No script matching 'Helper.setCookie' found.")
        except Exception as e:
            logger.error(f"Error parsing cookie: {e}")
            raise
