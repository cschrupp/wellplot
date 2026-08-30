"""Agentic natural-language compiler graph for Wellplot."""

from .executor import DirectIntentExecutionResult, execute_document_intent
from .finalization import (
    MAX_VISUAL_REPAIR_CYCLES,
    CanonicalDocumentRenderer,
    DocumentFinalizationResult,
    FinalRenderArtifact,
    VisualReviewer,
    VisualReviewRequest,
    VisualReviewResult,
    finalize_document_intent,
)
from .models import (
    CompilationMode,
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
from .revision import RevisionCompilationResult, compile_document_revision
from .section_worker import SectionCompiler
from .verifier import (
    DocumentIntentVerificationResult,
    IntentVerificationIssue,
    verify_document_intent,
)
from .workflow import ReconstructionGraphDependencies, build_compile_graph

__all__ = [
    "CompiledArtifact",
    "CompilationMode",
    "CanonicalDocumentRenderer",
    "DocumentFinalizationResult",
    "DocumentIntentVerificationResult",
    "DirectIntentExecutionResult",
    "ExistingProviderStructuredAdapter",
    "FinalRenderArtifact",
    "IntentVerificationIssue",
    "MAX_VISUAL_REPAIR_CYCLES",
    "ReconstructionDiagnostic",
    "ReconstructionGraphDependencies",
    "ReconstructionPlan",
    "ReconstructionPlanner",
    "RevisionCompilationResult",
    "ReportCompiler",
    "SectionCompiler",
    "SectionPlan",
    "SemanticComponentPlan",
    "StructuredModelProtocol",
    "VisualCorrection",
    "VisualReviewer",
    "VisualReviewRequest",
    "VisualReviewResult",
    "build_compile_graph",
    "compile_document_revision",
    "execute_document_intent",
    "finalize_document_intent",
    "verify_document_intent",
]
