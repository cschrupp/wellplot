from __future__ import annotations

from pathlib import Path

from ..errors import DependencyUnavailableError


def load_dlis(path: str | Path):
    try:
        import dlisio  # noqa: F401
    except ImportError as exc:
        raise DependencyUnavailableError(
            "DLIS ingestion requires dlisio. Install well-log-os[dlis]."
        ) from exc

    raise NotImplementedError(
        "DLIS normalization is scaffolded but not implemented yet. "
        "The package architecture already supports scalar, array, and raster channels."
    )
