class WellLogOSError(Exception):
    """Base exception for well_log_os."""


class DependencyUnavailableError(WellLogOSError):
    """Raised when an optional dependency is required but missing."""


class UnitConversionError(WellLogOSError):
    """Raised when a unit conversion cannot be performed safely."""


class TemplateValidationError(WellLogOSError):
    """Raised when a template cannot be converted into a document."""


class LayoutError(WellLogOSError):
    """Raised when a document cannot be placed on the requested page."""
