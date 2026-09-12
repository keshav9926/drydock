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


class StoreUnavailable(KeelError):
    """The journal itself could not be reached or written.

    Distinct from every other error here because it is the one failure a worker must *not* record.
    A program bug is a run failure and belongs in the journal; a store outage is a fact about the
    infrastructure, and writing `RUN_FAILED` because the disk blinked converts a transient problem
    into permanent data loss — with any effect that already landed now orphaned, since the journal
    says the run failed and the world says otherwise.

    The correct response is the one a crash gets: append nothing, release nothing, let the lease
    lapse, and let a successor read the journal and dispose of the open step by its effect class.
    Backends raise this in place of their driver's own error so a worker never has to know what a
    connection failure looks like in psycopg.
    """


class LeaseTooShort(KeelError):
    """lease_ttl <= max registered tool.timeout; the pre-dispatch gate could never clear (§8.4)."""


# --- effects -----------------------------------------------------------------
class DuplicateEffectKey(KeelError): ...


class UnknownTool(KeelError): ...


class AmbiguousRunRef(KeelError):
    """A prefix that matches more than one run. Distinct from "no such run" because the two ask
    the user for opposite things, and UUIDv7 makes this common: runs started seconds apart share a
    long leading prefix, so the obvious eight characters are often not enough."""

    def __init__(self, prefix: str, matches: int) -> None:
        super().__init__(f"{prefix!r} matches {matches} runs; use a longer prefix")
        self.prefix = prefix
        self.matches = matches


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


class UnknownOutcome(KeelError):
    """The receiver — a tool's, or a model provider's — did not answer, or answered that it could
    not: a 5xx, a dropped connection, a malformed reply.

    Epistemically identical to a timeout — the request left the process and the outcome is unknown
    — so the *class* decides what happens next, not the status code (§9.2). EXTERNAL becomes
    AMBIGUOUS and is disposed by its declared resolution; everything else is safe to re-execute.
    """


class Rejected(KeelError):
    """The receiver said no, definitively: a 4xx. That is knowledge, not ambiguity, so the step
    fails and is not retried for any class."""
