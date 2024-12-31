import json
import os
from pathlib import Path

# Define the path to the config directory
CONFIG_DIR = Path(__file__).parent

# Load configuration files
def load_config(file_name):
    config_path = CONFIG_DIR / file_name
    with open(config_path, 'r') as file:
        return json.load(file)

# Initialize configuration
config = {
    "logger_config": load_config("logger_config.py"),
    "config_sample": load_config("config.sample.json"),
    "postdata": load_config("postdata.json")
}
