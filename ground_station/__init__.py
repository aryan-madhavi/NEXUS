"""NEXUS Ground Station package.

Provides host-side connection management, protocol parsing, and telemetry ingestion
for the NEXUS Environmental Monitoring Project.
"""

__version__ = "0.1.0"

import os
from typing import Dict, Optional


def load_env_file(path: str = ".env") -> Dict[str, str]:
    """Parse key-value environment variables from a .env file safely without external dependencies.

    Args:
        path: Path to the .env file (default: '.env' in current working directory).

    Returns:
        Dictionary of parsed environment key-value pairs. Returns empty dict if file does not exist.
    """
    env: Dict[str, str] = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("'\"")
    return env

