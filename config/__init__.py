import json
import random
from pathlib import Path

# Define the path to the config directory
CONFIG_DIR = Path(__file__).parent

# Load configuration files
def load_config(file_name):
    config_path = CONFIG_DIR / file_name
    with open(config_path, 'r') as file:
        config = json.load(file)
        if "base_responses" in config and config["base_responses"]:
            config["base_response"] = random.choice(config["base_responses"])
        else:
            config["base_response"] = {}
        return config

# Initialize configuration
config = load_config("config.json")
