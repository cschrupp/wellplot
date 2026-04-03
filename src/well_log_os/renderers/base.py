###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

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
