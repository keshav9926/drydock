"""Runtime adapters. Thin by rule: no counter, no pre-send lookup, no retry, no dedup (§13.3)."""

from crashproof.adapters.base import (
    CanonicalResult,
    Claim,
    ConfigPin,
    Dependency,
    RuntimeAdapter,
    SutHandle,
)

__all__ = ["CanonicalResult", "Claim", "ConfigPin", "Dependency", "RuntimeAdapter", "SutHandle"]
