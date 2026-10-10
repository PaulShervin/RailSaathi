"""
RailSathi AI — Backend Configuration

Loads environment variables and provides validated configuration constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# === API Keys & AWS Credentials ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-west-2"))
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")

# === Rate Limiting ===
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

# === Flask ===
FLASK_ENV = os.getenv("FLASK_ENV", "development")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"

# === Gemini / LLM Model ===
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2048"))

# === Agent Controller Limits ===
MAX_AGENT_ROUNDS = int(os.getenv("MAX_AGENT_ROUNDS", "4"))
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "6"))
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "2000"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))

# === Logging ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = Path(os.getenv("LOG_DIR", str(Path(__file__).resolve().parent / "logs")))

# === Database ===
DB_PATH = Path(__file__).resolve().parent / "knowledge" / "railsaathi.db"

# === CORS ===
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
