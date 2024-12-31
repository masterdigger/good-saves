import re
from bs4 import BeautifulSoup
from loguru import logger
from http_client import HTTPClient


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
                    self.client.new_cookie((cookie_name, cookie_value), domain=self.host, path="/")
                    logger.info(f"New cookie set: {cookie_name}")
                else:
                    logger.warning("No matching cookie pattern found in script tag.")
            else:
                logger.warning("No script matching 'Helper.setCookie' found.")
        except Exception as e:
            logger.error(f"Error parsing cookie: {e}")
            raise

    def parse_and_set_cookies_from_js(self, response_text: str):
        """Extract and set cookies from JavaScript in the response text."""
        try:
            pattern = r'Helper\.setCookie\("([^"]+)",\s*"([^"]+)",\s*(true|false)\)'
            matches = re.findall(pattern, response_text)
            if matches:
                for match in matches:
                    cookie_name, cookie_value, _ = match
                    self.client.new_cookie((cookie_name, cookie_value), domain=self.host, path="/")
                    logger.info(f"New cookie set from JS: {cookie_name}")
            else:
                logger.warning("No matching cookie pattern found in response text.")
        except Exception as e:
            logger.error(f"Error parsing cookie from JS: {e}")
            raise
