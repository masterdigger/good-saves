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
from logger_config import setup_logger

# Setup logging
logger = setup_logger()

# Directory path
LOGS_DIR = Path("logs")

# File paths
CONFIG_FILE = Path("config.json")
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
        with open(RECENT_HEADERS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.recent_headers, f)
            logger.debug("Recent headers saved to file.")

    def get_recent_headers(self) -> List[Dict[str, str]]:
        """Load the most recent headers from a file."""
        if RECENT_HEADERS_FILE.exists():
            with open(RECENT_HEADERS_FILE, "r", encoding="utf-8") as f:
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
                pattern = r'Helper\.setCookie\("([^"]+)",\s*"([^"]+)",\s*(true|false))\)'
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


class FormHandler:
    """Handles form operations, including fetching dynamic values and submission."""

    def __init__(self, client: IHTTPClient, form_data: FormData, path: str, query_params: Optional[dict] = None, test_mode: bool = False):
        self.client = client
        self.form_data = form_data
        self.path = path
        self.query_params = query_params
        self.cookie_handler = CookieHandler(client=self.client, host=HOST)
        self.test_mode = test_mode
        logger.info("FormHandler initialized successfully.")

    def get_attrs(self, key: str) -> Dict[str, str]:
        """Return attributes for a given key from DATA_PARAMS."""
        attrs = dict(zip(DATA_PARAMS[key]["attrs"], DATA_PARAMS[key]["query"]))
        logger.debug(f"Attributes for key '{key}': {attrs}")
        return attrs

    def set_new_url(self, tag):
        """Set a new URL for the form submission."""
        url_object = urlparse(tag.get("action"))
        self.path = url_object.path
        self.query_params.clear()
        self.query_params = parse_qs(url_object.query)
        logger.info(f"Form submission URL updated to: {self.path}")

    def append_url_query(self, tag):
        """Append additional query parameters."""
        self.query_params["qs_actionMode"] = [tag.get("value", "")]
        self.query_params["qs_template"] = ["stage"]
        self.query_params["rq_xhr"] = ["31"]
        logger.debug(f"Updated query parameters: {self.query_params}")

    def fetch_dynamic_values(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Fetch dynamic values from the form and populate the POST data."""
        data = {}
        fr_data = {}

        try:
            for key, param in DATA_PARAMS.items():
                attrs = self.get_attrs(key)
                tag = soup.find(attrs=attrs)

                if not tag:
                    logger.warning(f"No matching element found for key: {key}, attributes: {attrs}")
                    continue

                if key in ["Project", "Location", "Good Save Type", "Good Save Category", "Good Save Classification", "Risk Category", "jquery"]:
                    if key == "Project" and tag.has_attr("name"):
                        value = tag.contents[1].get("value", "")
                    elif key == "jquery":
                        value = tag.next_sibling.get("value", "")
                    else:
                        value = BASE_RESPONSE.get(key, "")

                    data[tag["name"]] = [value]
                    fr_data[tag["name"]] = value

                    sibling = tag.parent.next_sibling
                    if sibling and sibling.has_attr("name"):
                        data[sibling["name"]] = [sibling.get("value", "")]
                        fr_data[sibling["name"]] = sibling.get("value", "")

                elif key == "upTextareaControl":
                    textareas = soup.find_all(attrs=attrs)
                    for i, textarea in enumerate(textareas):
                        value = BASE_RESPONSE[key][i]
                        data[textarea["name"]] = [value]
                        fr_data[textarea["name"]] = value

                elif key == "fr_ActionId":
                    self.append_url_query(tag)
                    value = tag.get("value", "")
                    data[tag["name"]] = [value]
                    fr_data[tag["name"]] = value

                elif key == "fr_formState":
                    value = tag.get("value")
                    data[tag["name"]] = [value]
                    fr_data[tag["name"]] = json.loads(value)

                elif key == "Submitted By":
                    value = BASE_RESPONSE.get(key, "Default User")
                    data[tag["name"]] = [value]
                    fr_data[tag["name"]] = value

                elif key == "Header_Container_AppMain":
                    fr_data["fr_formGuid"] = tag.get("class", "")[0][5:]
                    fr_data["fr_formName"] = tag.get("name", "")
                    fr_data["fr_uniqueId"] = tag.get("id", "")
                    self.set_new_url(tag)

                else:
                    value = tag.get("value", "")
                    data[tag["name"]] = [value]
                    if key not in ["CSRFToken", "fr_fupUniqueId"]:
                        fr_data[tag["name"]] = value

                logger.debug(f"Extracted data for key '{key}': {value}")

            data["fr_formData"] = [json.dumps([fr_data], separators=(',', ':'))]

            with open("postdata.json", "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
                logger.info("Dynamic form data saved to postdata.json.")

        except Exception as e:
            logger.error(f"Error while fetching dynamic values: {e}")
            raise

        return data

    def parse_cookie(self, soup: BeautifulSoup):
        """Extract and set cookies from JavaScript in the response."""
        try:
            script_tag = soup.find(string=re.compile("Helper.setCookie"))
            if script_tag:
                logger.info("JavaScript containing cookies found.")
                pattern = r'Helper\.setCookie"([^"]+)",\s*"([^"]+)",\s*(true|false)'
                match = re.search(pattern, script_tag)
                if match:
                    cookie_name, cookie_value, _ = match.groups()
                    self.client.new_cookie((cookie_name, cookie_value), domain=HOST, path="/")
                    logger.info(f"New cookie set: {cookie_name}={cookie_value}")
                else:
                    logger.warning("No matching cookie pattern found in script tag.")
            else:
                logger.warning("No script matching 'Helper.setCookie' found.")
        except Exception as e:
            logger.error(f"Error while parsing cookies: {e}")
            raise

    def submit_form(self) -> Optional[httpx.Response]:
        """Submit the form with the updated POST data."""
        try:
            response = self.client.get(self.path, params=self.query_params)
            logger.info("GET request completed successfully.")
            soup = BeautifulSoup(response.text, "lxml")
            self.parse_cookie(soup)
            updated_post_data = self.fetch_dynamic_values(soup)

            if not TEST_MODE:
                response = self.client.post(self.path, data=updated_post_data, params=self.query_params)
                logger.info("Form submission successful.")
                return response

            logger.info("Test mode enabled, POST request skipped.")
        except Exception as e:
            logger.error(f"Error during form submission: {e}")
            raise


if __name__ == "__main__":
    logger.info("Starting application.")

    try:
        with HTTPClient(base_url=BASE_URL, headers_list=HEADERS_LIST) as client:
            logger.info("HTTPClient initialized successfully.")

            response = client.get(PATH, params=QUERY_PARAMS)
            logger.info("Initial GET request successful.")

            soup = BeautifulSoup(response.text, "html.parser")
            form_handler = FormHandler(client=client, form_data=FormData(data={}), path=PATH, query_params=QUERY_PARAMS)

            form_handler.parse_cookie(soup)
            logger.info("Cookies parsed and set.")

            post_response = form_handler.submit_form()
            if post_response:
                logger.info(f"Form submitted successfully. Response: {post_response.text[:100]}...")
            else:
                logger.warning("No response received after form submission.")

    except Exception as e:
        logger.critical(f"Application terminated due to an error: {e}")