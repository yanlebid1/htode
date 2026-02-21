# common/utils/secrets.py
"""
Docker Secrets helper with environment variable fallback.

In Docker Compose, secrets are mounted as files at /run/secrets/<name>.
In local dev or CI, we fall back to plain environment variables.
"""

import os
from typing import Optional


def get_secret(name: str, fallback_env: Optional[str] = None, default: Optional[str] = None) -> Optional[str]:
    """
    Read a secret value, preferring Docker Secrets over env vars.

    Priority:
      1. /run/secrets/<name>  (Docker Secrets)
      2. os.getenv(fallback_env)  (environment variable)
      3. default

    Args:
        name: The Docker secret name (maps to /run/secrets/<name>).
        fallback_env: Environment variable name to use if secret file doesn't exist.
        default: Default value if neither source provides a value.
    """
    secret_path = f"/run/secrets/{name}"
    try:
        with open(secret_path) as f:
            value = f.read().strip()
            if value:
                return value
    except (FileNotFoundError, PermissionError):
        pass

    if fallback_env:
        env_value = os.getenv(fallback_env)
        if env_value is not None:
            return env_value

    return default
