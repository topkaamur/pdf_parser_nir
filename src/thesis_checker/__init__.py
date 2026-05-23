"""SPbPU thesis checker built on top of the lab4 PDF parser."""

from .engine import check_document, check_pdf_bytes, check_pdf_path
from .models import (
    CheckResult,
    CheckStatus,
    RuleConfidence,
    RuleSeverity,
    ThesisReport,
)

__all__ = [
    "check_document",
    "check_pdf_bytes",
    "check_pdf_path",
    "CheckResult",
    "CheckStatus",
    "RuleConfidence",
    "RuleSeverity",
    "ThesisReport",
]
