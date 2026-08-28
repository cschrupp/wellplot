"""Extensible authoring-capability registry."""

from .base import CapabilityCategory, CapabilitySpec
from .builtins import builtin_capabilities, create_builtin_registry
from .registry import CapabilityRegistry

__all__ = [
    "CapabilityCategory",
    "CapabilityRegistry",
    "CapabilitySpec",
    "builtin_capabilities",
    "create_builtin_registry",
]
