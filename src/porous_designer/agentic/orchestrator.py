"""Human-supervised natural-language interpretation orchestration."""

from __future__ import annotations

import uuid
from pathlib import Path

from porous_designer.agentic.audit import write_agentic_audit
from porous_designer.agentic.contracts import AgenticWorkflowStatus, ApprovalRecord, FieldReviewDecision, ParsedRequestResult
from porous_designer.agentic.provider import AgentProvider, NoLLMProvider
from porous_designer.agentic.provider_config import ProviderSettings
from porous_designer.agentic.request_parser_agent import RequestParserAgent
from porous_designer.agentic.review import apply_review_decisions, build_proposed_specification, create_approval_record
from porous_designer.domain.specification import DesignSpecification


class AgenticRequestOrchestrator:
    def __init__(self, provider: AgentProvider | None = None, *, audit_root: str | Path | None = None, settings: ProviderSettings | None = None) -> None:
        self.provider = provider or NoLLMProvider()
        self.settings = settings or ProviderSettings()
        if audit_root is None:
            from porous_designer.paths import runs_dir

            audit_root = runs_dir()
        self.audit_root = Path(audit_root)
        self.status = AgenticWorkflowStatus.REQUEST_NOT_PARSED
        self.last_request = ""
        self.last_result: ParsedRequestResult | None = None
        self.last_proposal: DesignSpecification | None = None
        self.last_approval: ApprovalRecord | None = None
        self.session_id = str(uuid.uuid4())

    @property
    def provider_status(self) -> str:
        if isinstance(self.provider, NoLLMProvider):
            return "Structured-only mode; no external provider required."
        if not getattr(self.provider, "enabled", False):
            return "External agent access disabled."
        return f"Provider available: {getattr(self.provider, 'name', 'provider')} / {getattr(self.provider, 'model', self.settings.selected_model())}"

    def parse_request(
        self,
        request: str,
        current_specification: DesignSpecification,
        *,
        provider: AgentProvider | None = None,
        settings: ProviderSettings | None = None,
    ) -> ParsedRequestResult:
        """Parse a request; ``provider``/``settings`` override for this call only."""
        self.status = AgenticWorkflowStatus.PARSING
        self.last_request = request
        agent = RequestParserAgent(provider or self.provider, settings=settings or self.settings)
        result = agent.parse(request)
        self.last_result = result
        self.last_proposal = build_proposed_specification(current_specification, result)
        self.status = AgenticWorkflowStatus.AMBIGUITIES_UNRESOLVED if any(a.mandatory and not a.resolved_choice for a in result.ambiguities) else AgenticWorkflowStatus.READY_FOR_APPROVAL
        write_agentic_audit(
            self.audit_dir,
            original_request=request,
            parsed=result,
            proposed_specification=self.last_proposal,
        )
        return result

    def approve(self, current_specification: DesignSpecification, decisions: list[FieldReviewDecision]) -> tuple[DesignSpecification, ApprovalRecord]:
        if self.last_result is None:
            raise RuntimeError("Parse a request before approving.")
        approved = apply_review_decisions(current_specification, self.last_result, decisions)
        resolutions = {a.identifier: a.resolved_choice or a.recommended_choice for a in self.last_result.ambiguities}
        record = create_approval_record(
            original_request=self.last_request,
            parsed=self.last_result,
            approved_specification=approved,
            decisions=decisions,
            ambiguity_resolutions=resolutions,
        )
        self.last_approval = record
        self.status = AgenticWorkflowStatus.HUMAN_APPROVED
        write_agentic_audit(
            self.audit_dir,
            original_request=self.last_request,
            parsed=self.last_result,
            proposed_specification=self.last_proposal or approved,
            approved_specification=approved,
            approval_record=record,
        )
        return approved, record

    def mark_approval_stale(self) -> None:
        if self.last_approval is not None:
            self.status = AgenticWorkflowStatus.APPROVAL_STALE

    @property
    def audit_dir(self) -> Path:
        return self.audit_root / self.session_id
