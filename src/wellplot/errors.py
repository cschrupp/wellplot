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

"""Project-specific exception hierarchy for wellplot."""


class WellLogOSError(Exception):
    """Base exception for wellplot."""


class DependencyUnavailableError(WellLogOSError):
    """Raised when an optional dependency is required but missing."""


class UnitConversionError(WellLogOSError):
    """Raised when a unit conversion cannot be performed safely."""


class TemplateValidationError(WellLogOSError):
    """Raised when a template cannot be converted into a document."""


class LayoutError(WellLogOSError):
    """Raised when a document cannot be placed on the requested page."""


class DatasetValidationError(WellLogOSError):
    """Raised when a dataset or channel violates the normalized data contract."""


class PathAccessError(WellLogOSError):
    """Raised when a requested path is inaccessible or outside an allowed root."""
