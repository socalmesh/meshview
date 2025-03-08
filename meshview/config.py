import configparser
import argparse

# Parse command-line arguments
parser = argparse.ArgumentParser(description="MeshView Configuration Loader")
parser.add_argument("--config", type=str, default="config.ini", help="Path to config.ini file (default: config.ini)")
args = parser.parse_args()

# Initialize config parser
config = configparser.ConfigParser()
if not config.read(args.config):
    raise FileNotFoundError(f"Config file '{args.config}' not found! Ensure the file exists.")

# MQTT settings
SERVER = config["MQTT"].get("SERVER", "localhost")
TOPICS = config["MQTT"].get("TOPICS", "").split(",")  # Convert to list
MQTT_PORT = int(config["MQTT"].get("PORT", 1883))
USERNAME = config["MQTT"].get("USERNAME", "")
PASSWORD = config["MQTT"].get("PASSWORD", "")

# Database settings
CONNECTION_STRING = config["DATABASE"].get("CONNECTION_STRING", "sqlite:///meshview.db")

# Server settings
BIND = config["SERVER"].get("BIND", "0.0.0.0")
WEB_PORT = int(config["SERVER"].get("PORT", 8080))
TLS_CERTS = config["SERVER"].get("TLS_CERTS", "")
ACME_CHALLENGE = config["SERVER"].get("ACME_CHALLENGE", "")

# Website settings
TITLE = config["WEBSITE"].get("TITLE", "MeshView")
