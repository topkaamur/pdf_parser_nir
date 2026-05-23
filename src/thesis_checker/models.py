"""Models for SPbPU thesis validation reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    MANUAL = "manual"


class RuleSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RuleConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class CheckResult:
    rule_id: str
    title: str
    category: str
    status: CheckStatus
    severity: RuleSeverity
    confidence: RuleConfidence
    message: str
    page: Optional[int] = None
    evidence: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category,
            "status": self.status.value,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "message": self.message,
            "page": self.page,
            "evidence": self.evidence,
        }


@dataclass
class DocumentLine:
    page_number: int
    text: str
    x_min: float
    y: float
    font_names: List[str] = field(default_factory=list)
    font_size: float = 0.0


@dataclass
class PageStats:
    page_number: int
    width: float
    height: float
    text_left: Optional[float] = None
    text_top: Optional[float] = None
    text_bottom: Optional[float] = None
    text_right: Optional[float] = None
    dominant_font_size: Optional[float] = None


@dataclass
class NormalizedDocument:
    num_pages: int
    metadata: Dict[str, str]
    version: str
    lines: List[DocumentLine]
    pages: List[PageStats]
    full_text: str
    file_size: Optional[int] = None

    def find_line(self, *needles: str) -> Optional[DocumentLine]:
        lowered = [needle.lower() for needle in needles]
        for line in self.lines:
            text = line.text.lower()
            if any(needle in text for needle in lowered):
                return line
        return None


@dataclass
class ThesisReport:
    source_file: Optional[str]
    strategy: str
    results: List[CheckResult]
    document: NormalizedDocument

    @property
    def passed(self) -> bool:
        return not any(result.status == CheckStatus.FAIL for result in self.results)

    def summary(self) -> Dict[str, int]:
        counts = {status.value: 0 for status in CheckStatus}
        for result in self.results:
            counts[result.status.value] += 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "strategy": self.strategy,
            "passed": self.passed,
            "summary": self.summary(),
            "results": [result.to_dict() for result in self.results],
            "document": {
                "version": self.document.version,
                "metadata": self.document.metadata,
                "num_pages": self.document.num_pages,
                "file_size": self.document.file_size,
            },
        }
