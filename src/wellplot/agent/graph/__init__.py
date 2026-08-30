"""Agentic natural-language compiler graph for Wellplot."""

from .executor import DirectIntentExecutionResult, execute_document_intent
from .models import (
    CompiledArtifact,
    ReconstructionDiagnostic,
    ReconstructionPlan,
    SectionPlan,
    SemanticComponentPlan,
    VisualCorrection,
)
from .planner import ReconstructionPlanner
from .provider_adapter import ExistingProviderStructuredAdapter, StructuredModelProtocol
from .report_worker import ReportCompiler
from .section_worker import SectionCompiler
from .verifier import (
    DocumentIntentVerificationResult,
    IntentVerificationIssue,
    verify_document_intent,
)
from .workflow import ReconstructionGraphDependencies, build_compile_graph

__all__ = [
    "CompiledArtifact",
    "DocumentIntentVerificationResult",
    "DirectIntentExecutionResult",
    "ExistingProviderStructuredAdapter",
    "IntentVerificationIssue",
    "ReconstructionDiagnostic",
    "ReconstructionGraphDependencies",
    "ReconstructionPlan",
    "ReconstructionPlanner",
    "ReportCompiler",
    "SectionCompiler",
    "SectionPlan",
    "SemanticComponentPlan",
    "StructuredModelProtocol",
    "VisualCorrection",
    "build_compile_graph",
    "execute_document_intent",
    "verify_document_intent",
]
