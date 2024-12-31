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
    """HTTP client for managing cookies and session."""

    def __init__(self, base_url: str, headers_list: List[Dict[str, str]], timeout: httpx.Timeout = httpx.Timeout(30.0, connect=15.0, read=60.0)):
        self.base_url = base_url
        self.headers_list = headers_list
        self.timeout = timeout
        self.recent_headers = self.get_recent_headers()
        self.random_headers = self.get_random_headers()
        self.session: Optional[httpx.Client] = None
        logger.info("HTTPClient initialized.")

    def __enter__(self) -> "HTTPClient":
        self.session = httpx.Client(base_url=self.base_url, headers=self.random_headers, follow_redirects=True, timeout=self.timeout)
        logger.info("HTTP session opened.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.session:
            self.session.close()
            logger.info("HTTP session closed.")
        with open(RECENT_HEADERS_FILE, "w") as f:
            json.dump(self.recent_headers, f)
            logger.debug("Recent headers saved to file.")

    def get_recent_headers(self) -> List[Dict[str, str]]:
        if RECENT_HEADERS_FILE.exists():
            with open(RECENT_HEADERS_FILE, "r") as f:
                headers = json.load(f)
                logger.debug("Loaded recent headers from file.")
                return headers
        return []

    def save_recent_headers(self, headers: Dict[str, str]):
        self.recent_headers.insert(0, headers)
        self.recent_headers = self.recent_headers[:3]
        logger.debug("Updated recent headers.")

    def get_random_headers(self) -> Dict[str, str]:
        candidate = None
        while not candidate or candidate in self.recent_headers:
            candidate = random.choice(self.headers_list)
        self.save_recent_headers(candidate)
        logger.debug(f"Selected headers: {candidate}")
        return candidate

    def new_cookie(self, value: Tuple[str, str], domain: str, path: str):
        self.session.cookies.set(value[0], value[1], domain=domain, path=path)
        logger.debug(f"Session cookies: {self.session.cookies}")

    def get(self, path: str, params: Optional[dict] = None) -> httpx.Response:
        try:
            logger.info(f"Sending GET request to {path} with params {params}")
            response = self.session.get(path, params=params, headers={"Upgrade-Insecure-Requests": "1"})
            logger.debug(f"GET Response: {response.status_code}")
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during GET: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error during GET: {e}")
            raise

    def post(self, path: str, data: dict, params: Optional[dict] = None) -> httpx.Response:
        try:
            logger.info(f"Sending POST request with data: {data}")
            logger.info(f"Sending POST request to {path} with params {params}")
            response = self.session.post(url=path, data=data, params=params)
            logger.debug(f"POST request succeeded: {response.text}")
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during POST: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error during POST: {e}")
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
        logger.info("FormHandler initialized.")

    def get_attrs(self, key: str) -> Dict[str, str]:
        """Return attributes for a given key from DATA_PARAMS."""
        return dict(zip(DATA_PARAMS[key]["attrs"], DATA_PARAMS[key]["query"]))
        self.cookie_handler.parse_and_set_cookies(soup)

    def set_new_url(self, url):
        url_object = urlparse(url.get("action"))
        self.path = url_object.path
        self.query_params.clear()
        self.query_params = parse_qs(url_object.query)

    def append_url_query(self, value):
        self.query_params["qs_actionMode"] = [value.get("value", "")]
        self.query_params["qs_template"] = ["stage"]
        self.query_params["rq_xhr"] = ["31"]

    def fetch_dynamic_values(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Fetch dynamic values from the form and populate the POST data."""
        template_keys = ["Location", "Good Save Type", "Good Save Category", "Good Save Classification", "Risk Category", "upTextareaControl", "Submitted By"]
        data = {}
        fr_data = {}
        try:
            for key, param in DATA_PARAMS.items():
                attrs = self.get_attrs(key)
                tag = soup.find(attrs=attrs)
                if not tag:
                    logger.warning(f"No matching tag found for key: {key}, attributes: {attrs}")
                    continue
                if key in ["Project", "Location", "Good Save Type", "Good Save Category", "Good Save Classification", "Risk Category", "jquery"]:
                    if key == "Project" and tag.has_attr("name"):
                        data[tag["name"]] = [tag.contents[1].get("value", "")]
                        fr_data[tag["name"]] = tag.contents[1].get("value", "")
                    elif key == "jquery":
                        data[tag.next_sibling["name"]] = [tag.next_sibling.get("value", "")]
                        fr_data[tag.next_sibling["name"]] = tag.next_sibling.get("value", "")
                    else:
                        data[tag["name"]] = [BASE_RESPONSE.get(key, "")]
                        fr_data[tag["name"]] = BASE_RESPONSE.get(key, "")
                    sibling = tag.parent.next_sibling
                    if sibling and sibling.has_attr("name"):
                        data[sibling["name"]] = [sibling.get("value", "")]
                        fr_data[sibling["name"]] = sibling.get("value", "")
                elif key == "upTextareaControl":
                    textareas = soup.find_all(attrs=attrs)
                    for i, textarea in enumerate(textareas):
                        data[textarea["name"]] = [BASE_RESPONSE[key][i]]
                        fr_data[textarea["name"]] = BASE_RESPONSE[key][i]
                elif key == "fr_ActionId":
                    self.append_url_query(tag)
                    data[tag["name"]] = [tag.get("value", "")]
                    fr_data[tag["name"]] = tag.get("value")
                elif key == "fr_formState":
                    data[tag["name"]] = [tag.get("value")]
                    fr_data[tag["name"]] = json.loads(tag.get("value"))
                elif key == "Submitted By":
                    data[tag["name"]] = [BASE_RESPONSE.get(key, "Salboheds")]
                    fr_data[tag["name"]] = BASE_RESPONSE.get(key, "Salboheds")
                elif key == "Header_Container_AppMain":
                    fr_data["fr_formGuid"] = tag.get("class", "")[0][5:]
                    fr_data["fr_formName"] = tag.get("name", "")
                    fr_data["fr_uniqueId"] = tag.get("id", "")
                    url_form_post = self.set_new_url(tag)
                else:
                    data[tag["name"]] = [tag.get("value", "")]
                    if key not in ["CSRFToken", "fr_fupUniqueId"]:
                        fr_data[tag["name"]] = tag.get("value", "")
                logger.debug(f"Extracted data for '{key}'.")
            data["fr_formData"] = [json.dumps([fr_data], separators=(',', ':'))]
            with open("postdata.json", "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Error fetching dynamic values: {e}")
            logger.debug(f"Extracted data in dict {data}")
            raise
        return data

    def parse_cookie(self, soup: BeautifulSoup):
        """Extract and set cookies from JavaScript in the response."""
        try:
            script_tag = soup.find(string=re.compile("Helper.setCookie"))
            if script_tag:
                logger.info("JavaScript containing cookies found.")
                pattern = r'Helper\.setCookie\("([^"]+)",\s*"([^"]+)",\s*(true|false)\)'
                match = re.search(pattern, script_tag)
                if match:
                    cookie_name, cookie_value, _ = match.groups()
                    self.client.new_cookie((cookie_name, cookie_value), domain=HOST, path="/")
                    logger.info(f"New cookie set: {cookie_name}")
                else:
                    logger.warning("No matching cookie pattern found in script tag.")
            else:
                logger.warning("No script matching 'Helper.setCookie' found.")
        except Exception as e:
            logger.error(f"Error parsing cookie: {e}")
            raise

    def submit_form(self) -> Optional[httpx.Response]:
        """Submit the form with the updated POST data."""
        try:
            response = self.client.get(self.path, params=self.query_params)
            logger.debug(f"Response headers: {response.headers}")
            logger.debug(f"Response request: {response.request.headers}")
            if response.status_code != httpx.codes.OK:
                logger.error(f"Failed GET request, status code: {response.status_code}")
                return None
            soup = BeautifulSoup(response.text, "lxml")
            with open(RESPONSE_HTML_FILE, "w") as file:
                file.write(str(soup))
            self.parse_cookie(soup)
            updated_post_data = self.fetch_dynamic_values(soup)
            if not TEST_MODE:
                response = self.client.post(path=self.path, data=updated_post_data, params=self.query_params)
                logger.debug(f"Response headers: {response.headers}")
                logger.debug(f"Response request: {response.request.headers}")
                if response.status_code != httpx.codes.OK:
                    logger.error(f"Failed GET request, status code: {response.status_code}")
                    return None
                logger.debug(f"Encode: {response.encoding}")
                soup = BeautifulSoup(response.text, "xml")
                with open(POST_RESPONSE_HTML_FILE, "w") as file:
                    file.write(str(soup))
                if response.status_code != httpx.codes.OK:
                    logger.error(f"Failed GET request, status code: {response.status_code}")
                    return None
                logger.info("Form successfully submitted.")
                return response
            logger.debug("Test mode active, POST request skipped.")
        except Exception as e:
            logger.exception("Failed to submit form.")
            raise


if __name__ == "__main__":
    try:
        form_data = FormData(data={})
        with HTTPClient(base_url=BASE_URL, headers_list=HEADERS_LIST) as client:
            logger.info(f"Using dynamic base_response: {BASE_RESPONSE}")
            form_handler = FormHandler(client=client, form_data=form_data, path=PATH, query_params=QUERY_PARAMS, test_mode=True)
            form_handler.submit_form()
    except ValidationError as val_err:
        logger.error(f"Validation error in FormData: {val_err}")
    except Exception as e:
        logger.critical(f"Critical error occurred: {e}")