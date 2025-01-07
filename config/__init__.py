import json
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "config.json"
"""# Define the path to the config directory


# Load configuration files
def load_config(file_name):
    config_path = CONFIG_DIR / file_name
    with open(config_path, "r") as file:
        return json.load(file)


# Initialize configuration
config = load_config("config.json")
"""


def load_config() -> (
    Tuple[
        str,
        str,
        str,
        Dict[str, List[str]],
        List[Dict[str, str]],
        Dict[str, Dict[str, Any]],
        Dict[str, Any],
    ]
):
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
    return (
        base_url,
        path,
        host,
        query_params,
        config["headers_list"],
        config["data_params"],
        base_response,
        config["form_post_url"],
        test_mode,
    )


(
    BASE_URL,
    PATH,
    HOST,
    QUERY_PARAMS,
    HEADERS_LIST,
    DATA_PARAMS,
    BASE_RESPONSE,
    FORM_POST_URL,
    TEST_MODE,
) = load_config()
