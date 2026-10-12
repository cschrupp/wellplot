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

"""Provider adapters for the public wellplot authoring API.

The canonical Code Mode engine imports provider-v2 modules directly. Legacy
tool-loop adapters remain available only through explicit compatibility
attribute access and are not loaded as a package side effect.
"""

__all__ = [
    "OpenAIAuthoringBackend",
    "OpenAICompatibleAuthoringBackend",
    "load_openai_api_key",
    "load_openai_compatible_api_key",
]


def __getattr__(name: str) -> object:
    """Load one legacy provider adapter only for explicit compatibility use."""
    if name in {"OpenAIAuthoringBackend", "load_openai_api_key"}:
        from . import openai

        return getattr(openai, name)
    if name in {"OpenAICompatibleAuthoringBackend", "load_openai_compatible_api_key"}:
        from . import openai_compat

        return getattr(openai_compat, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
