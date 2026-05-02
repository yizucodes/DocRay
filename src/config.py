"""Shared configuration for DocRay scripts."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v or not str(v).strip():
        raise EnvironmentError(f"{name} must be set in .env or the environment.")
    return v.strip()


# HydraDB
HYDRADB_API_KEY = _require_env("HYDRADB_API_KEY")
HYDRADB_TENANT_ID = os.environ.get("HYDRADB_TENANT_ID", "espn-corpus").strip()
HYDRADB_FEEDBACK_TENANT_ID = os.environ.get(
    "HYDRADB_FEEDBACK_TENANT_ID", "edited-outputs"
).strip()

# GMI Cloud (OpenAI-compatible)
GMI_API_KEY = _require_env("GMI_CLOUD_API_KEY")
GMI_BASE_URL = os.environ.get("GMI_CLOUD_BASE_URL", "https://api.gmi-serving.com/v1").strip()
GMI_MODEL = os.environ.get("GMI_CLOUD_MODEL", "deepseek-ai/DeepSeek-V3.2").strip()
