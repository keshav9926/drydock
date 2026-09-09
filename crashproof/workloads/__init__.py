"""Canonical workloads: runtime-neutral YAML plus the loader that validates it (§13.2)."""

from crashproof.workloads.spec import Workload, load, load_named

__all__ = ["Workload", "load", "load_named"]
