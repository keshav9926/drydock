# restate-sdk: `restate-sdk[pydantic-ai]` does not install what `import restate.ext.pydantic` needs

## Pre-filing notes (for the owner; delete this section before filing)

| | |
|---|---|
| Status | **draft, not filed** |
| Where | [restatedev/sdk-python](https://github.com/restatedev/sdk-python/issues) |
| Kind | A packaging bug with a two-line repro. It is not a Crashproof matrix finding: there is no row, no fairness level and no spec, so the template's matrix fields are replaced by a version table. |
| Verified | 2026-09-18, in throwaway venvs under WSL2 Ubuntu 24.04, Python 3.13, uv (created and deleted by the check). restate-sdk 1.0.5 is still the latest on PyPI. |

**Which project, and why this one.** The import that fails is restate-sdk's own: `restate/ext/pydantic/_toolset.py:14` does `from pydantic_ai.mcp import MCPToolset` at module level. The extra meant to make that module importable declares `pydantic-ai-slim>=2.0,<3` without `[mcp]`. pydantic-ai-slim is behaving as designed: MCP is an optional extra there, and it raises a clear ImportError naming the install that fixes it.

There was a second, pydantic-ai-side gap: at 2.43.0, `pydantic_ai/mcp.py:51` did `import httpx`, which `pydantic-ai-slim[mcp]` did not bring. It is **already fixed in pydantic-ai-slim 2.45.0**, where `pydantic_ai.mcp` imports with `[mcp]` and no httpx. So it is not filed. This repo's `restate` extra can drop its explicit `httpx` once it requires pydantic-ai-slim ≥ 2.45.

---

## Issue body

**Title:** `restate-sdk[pydantic-ai]`: `import restate.ext.pydantic` raises ImportError, because `pydantic_ai.mcp` is imported unconditionally and the extra does not install `pydantic-ai-slim[mcp]`

**What happens.** In a fresh environment:

```bash
uv venv /tmp/r && uv pip install --python /tmp/r/bin/python "restate-sdk[pydantic-ai]==1.0.5"
/tmp/r/bin/python -c "import restate.ext.pydantic"
```

```
ImportError: Please install the fastmcp client to use `MCPToolset` — `pip install "pydantic-ai-slim[mcp]"` pulls `fastmcp-slim[client]`, or install the full `fastmcp` package directly.
  restate/ext/pydantic/__init__.py:6: from ._agent import RestateAgent
  restate/ext/pydantic/_agent.py:36: from ._toolset import RestateContextRunToolSet
  restate/ext/pydantic/_toolset.py:14: from pydantic_ai.mcp import MCPToolset
  pydantic_ai/mcp.py:48: raise ImportError(
```

The extra resolved pydantic-ai-slim 2.45.0. The same happens with 2.43.0 (`pydantic_ai/mcp.py:43`).

| install (fresh venv, Python 3.13, Linux) | pydantic-ai-slim | `import restate.ext.pydantic` |
|---|---|---|
| `restate-sdk[pydantic-ai]==1.0.5` | 2.45.0 | ImportError (fastmcp client) |
| `restate-sdk==1.0.5 pydantic-ai-slim==2.43.0` | 2.43.0 | ImportError (fastmcp client) |
| `restate-sdk[pydantic-ai] pydantic-ai-slim[mcp]` | 2.45.0 | OK |
| `pydantic-ai==2.43.0 "restate_sdk[serde]==1.0.5"`: the install on [pydantic.dev's Restate page](https://pydantic.dev/docs/ai/integrations/durable_execution/restate/) | 2.43.0 (+ full `pydantic-ai`) | OK |

So the documented install works, because the full `pydantic-ai` package brings the MCP client. The `pydantic-ai` extra, and any environment that uses `pydantic-ai-slim`, does not. restate-sdk 1.0.5 declares `pydantic-ai-slim>=2.0,<3 ; extra == 'pydantic-ai'`.

**Why it matters.** An agent that uses no MCP server still needs the MCP client installed to import `RestateAgent`.

**Possible fixes (either).**

- Declare `pydantic-ai-slim[mcp]` in the `pydantic-ai` extra.
- Import `MCPToolset` lazily in `_toolset.py`, as `_agent.py:122` already does, so the MCP client is needed only when an MCP toolset is used.

**Found while** building a Restate arm for a crash-testing harness ([drydock](https://github.com/keshav9926/drydock)). Its `restate` extra works around this by naming `pydantic-ai-slim[mcp]` itself.
