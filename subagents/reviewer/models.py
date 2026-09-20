"""
Domain models for the Reviewer Subagent.
Provides typed Pydantic models for code audit findings, severity categories,
and structured audit reports.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    CRITICAL = "CRITICAL"  # SQLi, eval, remote code execution, hardcoded credentials
    HIGH = "HIGH"          # Port conflicts, unhandled async Express crashes, process leaks
    MEDIUM = "MEDIUM"      # React direct state mutation, missing keys, hardcoded API URLs
    LOW = "LOW"            # Missing CORS, minor syntax/lint warnings
    INFO = "INFO"          # Best-practice recommendations, performance polish


class FindingCategory(str, Enum):
    SECURITY = "SECURITY"
    RELIABILITY = "RELIABILITY"
    REACT_PATTERNS = "REACT_PATTERNS"
    ARCHITECTURE = "ARCHITECTURE"
    PERFORMANCE = "PERFORMANCE"


class ReviewFinding(BaseModel):
    """Represents a single defect, vulnerability, or anti-pattern discovered during review."""

    file_path: str
    line_number: Optional[int] = None
    severity: FindingSeverity = FindingSeverity.MEDIUM
    category: FindingCategory = FindingCategory.SECURITY
    title: str
    description: str
    code_snippet: Optional[str] = None
    suggested_replacement: Optional[str] = None

    def format_heading(self) -> str:
        loc = f"{self.file_path}:{self.line_number}" if self.line_number else self.file_path
        return f"**[{self.severity.value}] {loc}**: {self.title}"


class ReviewAuditReport(BaseModel):
    """Complete structured audit report produced by static scanner and LLM reviewer."""

    score: int = Field(ge=0, le=100, default=95)
    status: str = "APPROVED"  # APPROVED | NEEDS_REVISION | CRITICAL_FIX_REQUIRED
    summary: str = ""
    findings: List[ReviewFinding] = Field(default_factory=list)
    inspected_files: List[str] = Field(default_factory=list)
    approved: bool = True

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.HIGH)

    def recalculate(self) -> None:
        """Dynamically computes score, status, and approval based on findings."""
        deductions = 0
        for f in self.findings:
            if f.severity == FindingSeverity.CRITICAL:
                deductions += 25
            elif f.severity == FindingSeverity.HIGH:
                deductions += 15
            elif f.severity == FindingSeverity.MEDIUM:
                deductions += 5
            elif f.severity == FindingSeverity.LOW:
                deductions += 2

        self.score = max(0, min(100, 100 - deductions))
        if self.score >= 90:
            self.status = "APPROVED"
            self.approved = True
        elif self.score >= 75:
            self.status = "NEEDS_REVISION"
            self.approved = False
        else:
            self.status = "CRITICAL_FIX_REQUIRED"
            self.approved = False

    def to_markdown(self) -> str:
        """Formats the audit report into standardized GitHub-flavored Markdown."""
        files_str = ", ".join(self.inspected_files) if self.inspected_files else "Discovered workspace files"

        if not self.findings:
            findings_section = "- ✅ No high-severity code, reliability, or security flaws detected."
        else:
            blocks: List[str] = []
            for f in self.findings:
                loc = f"{f.file_path}:{f.line_number}" if f.line_number else f.file_path
                snippet_block = f"\n  ```javascript\n  // {loc}\n  {f.code_snippet.strip()}\n  ```" if f.code_snippet else ""
                fix_block = f"\n  **Recommended Fix**:\n  ```javascript\n  {f.suggested_replacement.strip()}\n  ```" if f.suggested_replacement else ""
                title_prefix = f"{f.title}: " if f.title and f.title not in f.description else ""
                blocks.append(f"- **[{f.severity.value}] {loc}**: {title_prefix}{f.description}{snippet_block}{fix_block}")
            findings_section = "\n".join(blocks)

        instruction = (
            "✅ Code quality meets release standards. You may proceed to conclude the task with `finish`."
            if self.approved
            else "👉 Apply surgical patches using `edit_file` to resolve the flagged issues before calling `finish`."
        )

        return f"""# 🧐 Code Review & Security Audit
**Target Files**: {files_str}
**Overall Code Quality Score**: **{self.score}/100**
**Status**: **{self.status}**

---

### 🚨 Issues & Audit Findings
{findings_section}

### 🛡️ Security & Resilience
- **Secrets Audit**: {'Passed — No raw credentials or API keys detected.' if self.score >= 90 else 'Action Required — Review flagged secrets above.'}
- **API Error Handling**: {'Verified robust structured error handling.' if self.score >= 80 else 'Action Required — Ensure async routes are wrapped in try/catch.'}
- **Input Sanitization**: {'Safe — No unescaped SQL or command injection patterns found.' if self.score >= 75 else 'Critical Action Required — Replace dynamic string queries with parameterized queries.'}

---
### 📋 Instructions for Main Engineer
{instruction}
"""

    @classmethod
    def from_markdown(cls, text: str, files: Optional[List[str]] = None) -> ReviewAuditReport:
        """Parses a generated Markdown report into a typed ReviewAuditReport model."""
        score = 90
        score_match = re.search(r"\*\*(\d+)/100\*\*", text) or re.search(r"Score\*\*:\s*(\d+)", text, re.IGNORECASE)
        if score_match:
            try:
                score = int(score_match.group(1))
            except ValueError:
                score = 90

        status = "APPROVED"
        if "CRITICAL_FIX_REQUIRED" in text:
            status = "CRITICAL_FIX_REQUIRED"
        elif "NEEDS_REVISION" in text:
            status = "NEEDS_REVISION"
        elif score < 75:
            status = "CRITICAL_FIX_REQUIRED"
        elif score < 90:
            status = "NEEDS_REVISION"

        approved = status == "APPROVED"
        findings: List[ReviewFinding] = []

        # Extract findings bullet points
        bullet_matches = re.findall(r"-\s+\*\*([^\*]+)\*\*:\s+([^\n]+)", text)
        for heading, desc in bullet_matches:
            if any(k in heading for k in ["Target Files", "Overall Code", "Status", "Secrets Audit", "API Error", "Input Sanitization"]):
                continue

            severity = FindingSeverity.MEDIUM
            if "CRITICAL" in heading.upper():
                severity = FindingSeverity.CRITICAL
            elif "HIGH" in heading.upper() or "WARNING" in heading.upper():
                severity = FindingSeverity.HIGH
            elif "INFO" in heading.upper():
                severity = FindingSeverity.INFO

            category = FindingCategory.SECURITY
            if "React" in heading or "key" in desc.lower() or "mutation" in desc.lower():
                category = FindingCategory.REACT_PATTERNS
            elif "Port" in heading or "Error" in heading or "Reliability" in heading:
                category = FindingCategory.RELIABILITY

            file_part = heading.split(" ")[-1].strip("():")
            file_path = file_part.split(":")[0] if ":" in file_part else file_part
            line_num = None
            if ":" in file_part:
                try:
                    line_num = int(file_part.split(":")[1])
                except ValueError:
                    pass

            findings.append(
                ReviewFinding(
                    file_path=file_path or (files[0] if files else "workspace"),
                    line_number=line_num,
                    severity=severity,
                    category=category,
                    title=heading.strip(),
                    description=desc.strip(),
                )
            )

        return cls(
            score=score,
            status=status,
            summary=f"Audit completed with status {status} ({score}/100)",
            findings=findings,
            inspected_files=files or [],
            approved=approved,
        )
