"""NEXUS Command Router and Application Launcher Package.

Provides canonical command registry validation, Ground Station command routing,
and secure allowlisted application launching.
"""

from .application_launcher import ApplicationLauncher, LaunchResult
from .command_registry import (
    CommandDestination,
    CommandDisposition,
    CommandRegistry,
    CommandRegistryEntry,
    StatusCode,
)
from .router import CommandRouter

__all__ = [
    "ApplicationLauncher",
    "CommandDestination",
    "CommandDisposition",
    "CommandRegistry",
    "CommandRegistryEntry",
    "CommandRouter",
    "LaunchResult",
    "StatusCode",
]
