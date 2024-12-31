import json
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup
from loguru import logger
from pydantic import BaseModel

from cookie_handler import CookieHandler
from http_client import IHTTPClient
from config import DATA_PARAMS, BASE_RESPONSE, HOST, TEST_MODE


class FormData(BaseModel):
    """Model to represent and validate form data."""
    data: Dict[str, Any]


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

            with open("config/postdata.json", "w", encoding="utf-8") as file:
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