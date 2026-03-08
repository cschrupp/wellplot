from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..model import LogDocument, WellDataset


@dataclass(slots=True)
class RenderResult:
    backend: str
    page_count: int
    artifact: Any | None = None
    output_path: Path | None = None


class Renderer(ABC):
    @abstractmethod
    def render(
        self,
        document: LogDocument,
        dataset: WellDataset,
        *,
        output_path: str | Path | None = None,
    ) -> RenderResult:
        raise NotImplementedError
