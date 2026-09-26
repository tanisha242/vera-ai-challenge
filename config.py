import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

# Server Settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# Bot Metadata
TEAM_NAME = os.getenv("TEAM_NAME", "Tanisha Joshi")
TEAM_MEMBERS = ["Tanisha Joshi"]
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-flash")
APPROACH_SUMMARY = "Deterministic Rule-Based State Machine + Vertical-Aware Grounded Composer"
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "tanishajoshi2462@gmail.com")
BOT_VERSION = "1.0.0"

# Dataset Settings
DATASET_DIR = Path(os.getenv("DATASET_DIR", BASE_DIR / "dataset_expanded"))
