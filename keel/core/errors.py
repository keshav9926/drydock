"""Every error the runtime raises by name (§23.1). One module so callers never guess a package."""

from __future__ import annotations


class KeelError(Exception):
    """Base for everything Keel raises."""


# --- program bugs (deterministic under replay) -------------------------------
class ConcurrentStepError(KeelError):
    """Two ctx.* calls in flight for one run. Steps are strictly sequential (§1)."""


class NondeterminismDetected(KeelError):
    def __init__(self, step_index: int, journaled: object, issued: object) -> None:
        super().__init__(
            f"step {step_index}: journal has {journaled!r}, program issued {issued!r}"
        )
        self.step_index = step_index
        self.journaled = journaled
        self.issued = issued


class PromptDrift(KeelError):
    """VERIFY-only warning; never raised during RECOVER (§1)."""


class StateSchemaMismatch(KeelError): ...


class IllegalTransition(KeelError): ...


# --- lease / control plane ---------------------------------------------------
class Fenced(KeelError):
    """The fence UPDATE matched 0 rows. This worker writes nothing more for this run (§2)."""


class LeaseTooShort(KeelError):
    """lease_ttl <= max registered tool.timeout; the pre-dispatch gate could never clear (§8.4)."""


# --- effects -----------------------------------------------------------------
class DuplicateEffectKey(KeelError): ...


class UnknownTool(KeelError): ...


class ToolRegistrationError(KeelError): ...


class ToolFailed(KeelError): ...


class ToolAmbiguous(KeelError):
    """Transport error or timeout on an EXTERNAL tool: W3 with the worker still alive (§8.5)."""


class MissingCredential(KeelError): ...


class StepFailed(KeelError):
    def __init__(self, step_index: int, error: str, *, retryable: bool = False) -> None:
        super().__init__(f"step {step_index}: {error}")
        self.step_index = step_index
        self.error = error
        self.retryable = retryable


# --- budget / policy / lifecycle (v1 mechanisms, names fixed on day 1) -------
class BudgetExceeded(KeelError): ...


class DeadlineExceeded(KeelError): ...


class Cancelled(KeelError): ...


class PolicyDenied(KeelError): ...


class PolicyTimeout(KeelError): ...


class ApprovalBindingError(KeelError): ...


class ApprovalRejected(KeelError): ...


class ApprovalExpired(KeelError): ...


class ContractViolation(KeelError): ...


class ContractInvalid(KeelError): ...


class EffectDeniedInFork(KeelError): ...


class ForkOverrideBeforeFork(KeelError): ...


class ForkWithLiveChildren(KeelError): ...
