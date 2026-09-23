"""Extensible authoring-capability registry."""

from .base import (
    CapabilityCategory,
    CapabilityHandler,
    CapabilitySemanticMapping,
    CapabilitySemanticMetadata,
    CapabilitySpec,
)
from .builtins import builtin_capabilities, create_builtin_registry
from .registry import CapabilityRegistry

__all__ = [
    "CapabilityCategory",
    "CapabilityHandler",
    "CapabilitySemanticMapping",
    "CapabilitySemanticMetadata",
    "CapabilityRegistry",
    "CapabilitySpec",
    "builtin_capabilities",
    "create_builtin_registry",
]
