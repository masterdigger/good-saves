import json
import random
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import parse_qs, urlparse

import httpx
from loguru import logger
from pydantic import BaseModel


class IHTTPClient(ABC):
    @abstractmethod
    def get(self, path: str, params: Optional[dict] = None) -> httpx.Response:
        pass

    @abstractmethod
    def post(self, path: str, data: dict, params: Optional[dict] = None) -> httpx.Response:
        pass


class HTTPClient(IHTTPClient):
    """HTTP client for handling cookies and session operations."""

    def __init__(self, base_url: str, headers_list: List[Dict[str, str]], timeout: httpx.Timeout = httpx.Timeout(30.0, connect=15.0, read=60.0)):
        self.base_url = base_url
        self.headers_list = headers_list
        self.timeout = timeout
        self.recent_headers = self.get_recent_headers()
        self.random_headers = self.get_random_headers()
        self.session: Optional[httpx.Client] = None
        logger.info(f"HTTPClient initialized with base_url: {self.base_url}")

    def __enter__(self) -> "HTTPClient":
        self.session = httpx.Client(base_url=self.base_url, headers=self.random_headers, follow_redirects=True, timeout=self.timeout)
        logger.info("HTTP session started.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.session:
            self.session.close()
            logger.info("HTTP session closed.")
        with open("recent_headers.json", "w", encoding="utf-8") as f:
            json.dump(self.recent_headers, f)
            logger.debug("Recent headers saved to file.")

    def get_recent_headers(self) -> List[Dict[str, str]]:
        """Load the most recent headers from a file."""
        if Path("recent_headers.json").exists():
            with open("recent_headers.json", "r", encoding="utf-8") as f:
                headers = json.load(f)
                logger.debug("Recent headers loaded from file.")
                return headers
        logger.warning("No file with recent headers found.")
        return []

    def save_recent_headers(self, headers: Dict[str, str]):
        """Save the current headers to the recent headers list."""
        self.recent_headers.insert(0, headers)
        self.recent_headers = self.recent_headers[:3]  # Keep only the latest three headers
        logger.debug(f"Updated recent headers: {self.recent_headers}")

    def get_random_headers(self) -> Dict[str, str]:
        """Select random headers from the available list."""
        candidate = None
        while not candidate or candidate in self.recent_headers:
            candidate = random.choice(self.headers_list)
        self.save_recent_headers(candidate)
        logger.debug(f"Selected headers: {candidate}")
        return candidate

    def new_cookie(self, value: Tuple[str, str], domain: str, path: str):
        """Set a new cookie in the session."""
        self.session.cookies.set(value[0], value[1], domain=domain, path=path)
        logger.debug(f"New cookie set: {value[0]}={value[1]}")

    def get(self, path: str, params: Optional[dict] = None) -> httpx.Response:
        """Send a GET request to the specified path."""
        try:
            logger.info(f"Sending GET request to {path} with params {params}")
            response = self.session.get(path, params=params)
            logger.debug(f"GET response: {response.status_code}, content preview: {response.text[:100]}...")
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during GET request: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error during GET request: {e}")
            raise

    def post(self, path: str, data: dict, params: Optional[dict] = None) -> httpx.Response:
        """Send a POST request to the specified path."""
        try:
            logger.info(f"Sending POST request to {path} with data {data} and params {params}")
            response = self.session.post(path, data=data, params=params)
            logger.debug(f"POST response: {response.status_code}, content preview: {response.text[:100]}...")
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during POST request: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error during POST request: {e}")
            raise
