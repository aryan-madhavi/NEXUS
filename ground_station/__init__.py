"""NEXUS Ground Station package.

Provides host-side connection management, protocol parsing, and telemetry ingestion
for the NEXUS Environmental Monitoring Project.
"""

__version__ = "0.1.0"

import os
from typing import Dict, Optional


def load_env_file(path: Optional[str] = None) -> Dict[str, str]:
    """Parse key-value environment variables from a .env file safely without external dependencies.

    Args:
        path: Path to the .env file. If None, checks '.env' in CWD, then falls back to project root '.env'.

    Returns:
        Dictionary of parsed environment key-value pairs. Returns empty dict if file does not exist.
    """
    env: Dict[str, str] = {}
    target_path = path
    if target_path is None:
        if os.path.exists(".env"):
            target_path = ".env"
        else:
            default_project_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            if os.path.exists(default_project_env):
                target_path = default_project_env

    if target_path and os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("'\"")
    return env

