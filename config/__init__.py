import json
from pathlib import Path

# Define the path to the config directory
CONFIG_DIR = Path(__file__).parent

# Load configuration files
def load_config(file_name):
    config_path = CONFIG_DIR / file_name
    with open(config_path, 'r') as file:
        return json.load(file)

# Initialize configuration
config = load_config("config.json")
