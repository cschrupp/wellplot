"""Extensible authoring-capability registry."""

from .base import CapabilityCategory, CapabilityHandler, CapabilitySpec
from .builtins import builtin_capabilities, create_builtin_registry
from .registry import CapabilityRegistry

__all__ = [
    "CapabilityCategory",
    "CapabilityHandler",
    "CapabilityRegistry",
    "CapabilitySpec",
    "builtin_capabilities",
    "create_builtin_registry",
]
