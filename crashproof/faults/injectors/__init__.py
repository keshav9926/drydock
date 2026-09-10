"""Injectors: `shim` at MVP, `hook` at phase 6, `proxy` at week 2 (§27.7)."""

from crashproof.faults.injectors.base import Injector
from crashproof.faults.injectors.shim import ToolShim

__all__ = ["Injector", "ToolShim"]
