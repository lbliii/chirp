"""Human-in-the-loop tool approval — session-backed pending gates."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from chirp.errors import ChirpError

ApprovalStatus = Literal["pending", "approved", "denied"]


class ToolApprovalError(ChirpError):
    """Raised when a tool requires human approval before execution."""

    def __init__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        approval_id: str | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.arguments = arguments
        self.approval_id = approval_id
        detail = f"Tool {tool_name!r} requires human approval"
        if approval_id:
            detail = f"{detail} (approval_id={approval_id})"
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class PendingToolApproval:
    """One tool invocation awaiting or completing human review."""

    approval_id: str
    thread_id: str
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: ApprovalStatus = "pending"


@runtime_checkable
class ToolApprovalStore(Protocol):
    """Persist pending tool approvals keyed by approval_id."""

    async def create(
        self,
        *,
        thread_id: str,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> PendingToolApproval: ...

    async def get(self, approval_id: str) -> PendingToolApproval | None: ...

    async def mark_approved(self, approval_id: str) -> PendingToolApproval: ...

    async def mark_denied(self, approval_id: str) -> PendingToolApproval: ...

    async def consume(self, approval_id: str) -> PendingToolApproval | None:
        """Return and remove a terminal (approved/denied) approval."""
        ...


def _new_approval_id() -> str:
    return secrets.token_urlsafe(16)


class InMemoryToolApprovalStore:
    """Process-local approval store for tests and demos."""

    __slots__ = ("_pending",)

    def __init__(self) -> None:
        self._pending: dict[str, PendingToolApproval] = {}

    async def create(
        self,
        *,
        thread_id: str,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> PendingToolApproval:
        approval = PendingToolApproval(
            approval_id=_new_approval_id(),
            thread_id=thread_id,
            call_id=call_id,
            tool_name=tool_name,
            arguments=dict(arguments),
        )
        self._pending[approval.approval_id] = approval
        return approval

    async def get(self, approval_id: str) -> PendingToolApproval | None:
        return self._pending.get(approval_id)

    async def mark_approved(self, approval_id: str) -> PendingToolApproval:
        current = self._pending.get(approval_id)
        if current is None:
            msg = f"Unknown approval_id: {approval_id!r}"
            raise KeyError(msg)
        updated = PendingToolApproval(
            approval_id=current.approval_id,
            thread_id=current.thread_id,
            call_id=current.call_id,
            tool_name=current.tool_name,
            arguments=current.arguments,
            status="approved",
        )
        self._pending[approval_id] = updated
        return updated

    async def mark_denied(self, approval_id: str) -> PendingToolApproval:
        current = self._pending.get(approval_id)
        if current is None:
            msg = f"Unknown approval_id: {approval_id!r}"
            raise KeyError(msg)
        updated = PendingToolApproval(
            approval_id=current.approval_id,
            thread_id=current.thread_id,
            call_id=current.call_id,
            tool_name=current.tool_name,
            arguments=current.arguments,
            status="denied",
        )
        self._pending[approval_id] = updated
        return updated

    async def consume(self, approval_id: str) -> PendingToolApproval | None:
        current = self._pending.pop(approval_id, None)
        if current is None or current.status == "pending":
            if current is not None:
                self._pending[approval_id] = current
            return None
        return current


class SessionToolApprovalStore:
    """Persist pending approvals in the server session."""

    __slots__ = ("_session_key",)

    def __init__(self, session_key: str = "chirp_tool_approvals") -> None:
        self._session_key = session_key

    def _load_map(self) -> dict[str, PendingToolApproval]:
        from chirp.middleware.sessions import get_session

        session = get_session()
        raw = session.get(self._session_key) or {}
        loaded: dict[str, PendingToolApproval] = {}
        for approval_id, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            loaded[approval_id] = PendingToolApproval(
                approval_id=str(payload["approval_id"]),
                thread_id=str(payload["thread_id"]),
                call_id=str(payload["call_id"]),
                tool_name=str(payload["tool_name"]),
                arguments=dict(payload.get("arguments") or {}),
                status=payload.get("status", "pending"),
            )
        return loaded

    def _save_map(self, approvals: dict[str, PendingToolApproval]) -> None:
        from chirp.middleware.sessions import get_session

        session = get_session()
        session[self._session_key] = {
            approval_id: {
                "approval_id": item.approval_id,
                "thread_id": item.thread_id,
                "call_id": item.call_id,
                "tool_name": item.tool_name,
                "arguments": item.arguments,
                "status": item.status,
            }
            for approval_id, item in approvals.items()
        }

    async def create(
        self,
        *,
        thread_id: str,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> PendingToolApproval:
        approvals = self._load_map()
        approval = PendingToolApproval(
            approval_id=_new_approval_id(),
            thread_id=thread_id,
            call_id=call_id,
            tool_name=tool_name,
            arguments=dict(arguments),
        )
        approvals[approval.approval_id] = approval
        self._save_map(approvals)
        return approval

    async def get(self, approval_id: str) -> PendingToolApproval | None:
        return self._load_map().get(approval_id)

    async def mark_approved(self, approval_id: str) -> PendingToolApproval:
        approvals = self._load_map()
        current = approvals.get(approval_id)
        if current is None:
            msg = f"Unknown approval_id: {approval_id!r}"
            raise KeyError(msg)
        updated = PendingToolApproval(
            approval_id=current.approval_id,
            thread_id=current.thread_id,
            call_id=current.call_id,
            tool_name=current.tool_name,
            arguments=current.arguments,
            status="approved",
        )
        approvals[approval_id] = updated
        self._save_map(approvals)
        return updated

    async def mark_denied(self, approval_id: str) -> PendingToolApproval:
        approvals = self._load_map()
        current = approvals.get(approval_id)
        if current is None:
            msg = f"Unknown approval_id: {approval_id!r}"
            raise KeyError(msg)
        updated = PendingToolApproval(
            approval_id=current.approval_id,
            thread_id=current.thread_id,
            call_id=current.call_id,
            tool_name=current.tool_name,
            arguments=current.arguments,
            status="denied",
        )
        approvals[approval_id] = updated
        self._save_map(approvals)
        return updated

    async def consume(self, approval_id: str) -> PendingToolApproval | None:
        approvals = self._load_map()
        current = approvals.pop(approval_id, None)
        if current is None or current.status == "pending":
            if current is not None:
                approvals[approval_id] = current
                self._save_map(approvals)
            return None
        self._save_map(approvals)
        return current
