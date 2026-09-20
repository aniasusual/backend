# Dynamic Context Management: Implementation Roadmap & Specification

**Document Version:** 2.1.0  
**Target System:** Lowkey Multi-Agent Engineering Architecture  
**Created:** September 13, 2026  
**Status:** 100% Completed (All 13 Items Implemented)  

---

## 1. Executive Summary & Complete Compliance Matrix

This document defines the exhaustive, 13-point actionable implementation plan to upgrade Lowkey's context management engine from its baseline implementation (~48% compliance) to **100% compliance** with the **Dynamic Context Management System Specification (v2.0.0)**.

```
┌────────────────────────────────────────────────────────────────────────┐
│               UPGRADED CONTEXT MANAGEMENT ARCHITECTURE                 │
│                                                                        │
│  ┌───────────────────────────┐  ┌───────────────────────────────────┐  │
│  │ STATIC LAYER (CP-101.1)   │  │ DYNAMIC LAYER / RAM (CP-101.2)    │  │
│  │ - Pinned System Identity  │  │ - JIT Mounted Files Register      │  │
│  │ - .agentrules / AGENTS.md │  │ - 60% Window Budget Cap           │  │
│  │ - Active Runtime URLs/Ports│ │ - AST Slices & Signatures         │  │
│  │ - < 1,500 Token Budget    │  │ - Explicit mount/close lifecycle  │  │
│  └───────────────────────────┘  └───────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ EPHEMERAL LAYER (CP-101.3, CP-103)                               │  │
│  │ - Rolling Chat History (Clean User / Assistant turns)            │  │
│  │ - Immediate Ingestion Compression (>1.8k chars: 35 head / 35 tail│  │
│  │ - Rolling FIFO Budget Eviction + Alert Markers                   │  │
│  │ - Milestone Roll-ups (Purge resolved execution loops)            │  │
│  │ - Full Model Context Allocation (num_ctx: 32k - 256k)            │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

| Code | Architectural Module | Spec Pointer | Current Lowkey Status | Target State | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **ITEM-1** | Ollama Context Window Allocation (`num_ctx`) | [CP-106] | Missing in `CodingHarness`; defaults to 2k/4k tokens | Pass `num_ctx = config.context_window` on every chat call | [x] Completed |
| **ITEM-2** | Full Tool Schema Accounting in `TokenEstimator` | [CP-106] | Ignored in estimator; 3.6k tokens unaccounted for | Include active tool schemas in `estimate_total()` | [x] Completed |
| **ITEM-3** | Static Layer Repo Discovery (`.agentrules`, `AGENTS.md`) | [CP-101.1] | Hardcoded prompt only; ignores project-level rules | Dynamically discover and mount project rules into Static Layer (<1.5k tokens) | [x] Completed |
| **ITEM-4** | Ingestion-Time Tool Compression Pipeline (`record_interaction`) | [CP-103.1, Sec 3] | Naive 500-char middle slice after 3 turns | Compress outputs >1.8k chars immediately upon generation (35 head / 35 tail lines) | [x] Completed |
| **ITEM-5** | Safe Range Bounds on File Reading (`read_file`) | [CP-102.1] | No ceiling; reads entire files up to limits | Clamp unbounded reads to 250 lines max with pagination notices | [x] Completed |
| **ITEM-6** | Topology Discovery Tool (`locate_files_by_pattern`) | [CP-102.1] | Flat single-directory listing only | Depth-limited hierarchical tree exploration without line reading | [x] Completed |
| **ITEM-7** | Dynamic Virtual RAM Layer with 60% Budget Cap | [CP-101.2] | Files dumped into chat history as ephemeral tool results | Structured `mounted_virtual_ram` register in system frame with 60% context cap | [x] Completed |
| **ITEM-8** | File Mount Lifecycle Tools (`mount_file`, `unmount_file`/`close_file`) | [Sec 3] | No mount/unmount tool primitives | Expose explicit tools for model to mount active files and release attention | [x] Completed |
| **ITEM-9** | AST Code Signature Harvesting (`extract_signatures`) | [CP-105.2] | Zero AST parsing; model must ingest full raw files | Lightweight AST signature harvester stripping bodies, saving 90% tokens | [x] Completed |
| **ITEM-10**| Repository Dependency & Import/Export Graph Mapping | [CP-105.1] | No structural code analysis across files | Static analyzer mapping symbols, exports, and import relationships | [x] Completed |
| **ITEM-11**| Rolling FIFO Eviction & Alert Injection (`_enforce_rolling_budget`) | [CP-103.2, CP-106] | Arbitrary 30-turn clamp; no sliding eviction marker | Evict oldest turns on budget overflow and inject `[Context System Alert]` | [x] Completed |
| **ITEM-12**| Structured Tool Retention & Milestone Roll-ups | [CP-103.2] | All tool results deleted on turn compaction (amnesia bug) | Retain critical errors across user turns and roll up resolved intra-turn loops | [x] Completed |
| **ITEM-13**| Real-Time Context Telemetry & UI Gauge | [CP-106] | Raw JSON debug only; no token/window usage gauge | Emit token counts, dynamic RAM usage, window %, and compaction events to UI | [x] Completed |

---

## 2. Detailed Specification for Each Item

### ITEM-1: Ollama Context Window Allocation (`num_ctx`)
* **Spec Pointer:** [CP-106]
* **Affected Files:** `backend/plugins/coding_harness.py`, `backend/context/config.py`
* **Problem:** In `CodingHarness.process_prompt()`, `client.chat()` is called with `options={"temperature": 0.5}` without `num_ctx`. Ollama defaults to 2,048 or 4,096 tokens, silently clipping 32k/128k contexts.
* **Target:** Pass `options={"temperature": 0.5, "num_ctx": config.context_window}` to `client.chat()`.
* **Verification:** Unit test asserting `num_ctx` matches `get_model_context_window(model_name)`.

---

### ITEM-2: Full Tool Schema Accounting in `TokenEstimator`
* **Spec Pointer:** [CP-106]
* **Affected Files:** `backend/context/estimator.py`, `backend/context/manager.py`, `backend/tests/test_context_engine.py`
* **Problem:** `TokenEstimator.estimate_total()` ignores the 18 tool JSON schemas (~3,600 tokens), causing threshold checks to trigger far too late.
* **Target:** Add `estimate_schemas(schemas)` and incorporate it into `estimate_total(messages, system_prompt, schemas)`.
* **Verification:** Test proving `estimate_total` reflects schema tokens accurately.

---

### ITEM-3: Static Layer Repo Discovery (`.agentrules`, `AGENTS.md`)
* **Spec Pointer:** [CP-101.1]
* **Affected Files:** `backend/context/manager.py`, `backend/config/prompts.py`, `backend/tests/test_context_engine.py`
* **Problem:** Lowkey uses a hardcoded prompt string and ignores repository-level instructions (`.agentrules`, `AGENTS.md`, `README.md`).
* **Target:** Scan the project root for rule files on turn preparation, format into a bounded block (`< 1,500 tokens`), and prepend to the Static Layer.
* **Verification:** Test verifying `.agentrules` content appears in the system prompt with strict token bounding.

---

### ITEM-4: Ingestion-Time Tool Compression Pipeline (`record_interaction`)
* **Spec Pointer:** [CP-103.1, Section 3]
* **Affected Files:** `backend/context/squasher.py`, `backend/plugins/coding_harness.py`, `backend/tests/test_context_engine.py`
* **Problem:** Large tool outputs sit raw in the message queue until lazy squashing triggers, and squashing uses a naive 500-character middle slice that cuts mid-line and destroys stack traces.
* **Target:** Compress tool outputs $>1,800$ characters immediately upon generation in `CodingHarness`. Preserve the top 35 lines (header/init) and bottom 35 lines (stack trace/exit status), with an explicit omitted lines notice.
* **Verification:** Slicing tests ensuring no mid-line character cuts and preservation of error boundaries.

---

### ITEM-5: Safe Range Bounds on File Reading (`read_file`)
* **Spec Pointer:** [CP-102.1]
* **Affected Files:** `backend/tools/file_tools.py`, `backend/tools/schemas.py`, `backend/tests/test_file_tools.py`
* **Problem:** `read_file` has no default range limit, allowing the agent to ingest multi-thousand-line files in one call.
* **Target:** Clamp unbounded reads to 250 lines max. Return `[Lines 1-250 shown. File has {total} lines. Use read_file(start_line=251) to continue.]`.
* **Verification:** Test reading 1,000-line file without arguments returns exactly 250 lines + notice.

---

### ITEM-6: Topology Discovery Tool (`locate_files_by_pattern`)
* **Spec Pointer:** [CP-102.1]
* **Affected Files:** `backend/tools/file_tools.py`, `backend/tools/schemas.py`, `backend/tools/registry.py`
* **Problem:** Lowkey has `list_directory` (flat) and `glob_files`, but lacks a hierarchical, depth-limited topology tree tool.
* **Target:** Implement `locate_files_by_pattern(directory=".", max_depth=3, pattern="*")` returning a clean, indented visual file tree.
* **Verification:** Test verifying tree formatting and depth truncation.

---

### ITEM-7: Dynamic Virtual RAM Layer with 60% Budget Cap
* **Spec Pointer:** [CP-101.2]
* **Affected Files:** `backend/context/manager.py`, `backend/plugins/coding_harness.py`
* **Problem:** Files are dumped into chronological chat messages rather than managed as a dynamic workspace register.
* **Target:** Maintain `mounted_virtual_ram: Dict[str, str]` inside `ContextManager`. Render mounted files in a dedicated `[DYNAMIC ENVIRONMENT RAM REGISTER]` system block. Enforce that mounted RAM cannot exceed 60% of the model's context window.
* **Verification:** Test mounting and unmounting files, verifying dynamic system block generation and 60% ceiling rejection.

---

### ITEM-8: File Mount Lifecycle Tools (`mount_file`, `unmount_file`/`close_file`)
* **Spec Pointer:** [Section 3]
* **Affected Files:** `backend/tools/file_tools.py`, `backend/tools/schemas.py`, `backend/tools/registry.py`
* **Problem:** The model cannot explicitly mount or unmount files to manage its own attention window.
* **Target:** Provide `mount_file(file_path)` and `unmount_file(file_path)` / `close_file(file_path)` tools exposed to the LLM.
* **Verification:** Agent tool execution tests mounting files to RAM and unmounting when task finishes.

---

### ITEM-9: AST Code Signature Harvesting (`extract_signatures`)
* **Spec Pointer:** [CP-105.2]
* **Affected Files:** `backend/tools/ast_tools.py` (New), `backend/tools/schemas.py`, `backend/tools/registry.py`
* **Problem:** To inspect helper functions, route definitions, or component props, the agent must read entire file implementations, wasting 90% of tokens.
* **Target:** Implement AST signature extractor for JS/TS/JSX (exports, function headers, Express routes) and Python (classes, methods, docstrings) that strips function bodies.
* **Verification:** Test confirming `extract_signatures("server/index.js")` yields routes and signatures with zero body lines (>80% token savings).

---

### ITEM-10: Repository Dependency & Import/Export Graph Mapping
* **Spec Pointer:** [CP-105.1]
* **Affected Files:** `backend/tools/ast_tools.py`, `backend/tools/schemas.py`, `backend/tools/registry.py`
* **Problem:** The agent cannot determine which components or modules depend on an edited file without manual grep searches.
* **Target:** Add `map_dependencies(target_file: Optional[str] = None)` tool scanning the workspace AST to return an import/export dependency map.
* **Verification:** Test mapping a multi-file React/Express project correctly resolves imports and dependent files.

---

### ITEM-11: Rolling FIFO Eviction & Alert Injection (`_enforce_rolling_budget`)
* **Spec Pointer:** [CP-103.2, CP-106]
* **Affected Files:** `backend/context/manager.py`, `backend/tests/test_context_engine.py`
* **Problem:** Lowkey's safety clamp simply truncates messages past 30 turns without injecting a continuity marker or evaluating rolling token capacity.
* **Target:** Implement rolling FIFO eviction loop matching CP-106: when total tokens exceed target budget, pop earliest ephemeral turns and inject `[Context System Alert: Historical logs pruned due to token budget caps.]`.
* **Verification:** Test confirming sliding FIFO eviction maintains index 0 system instruction and injects alert marker.

---

### ITEM-12: Structured Tool Retention & Milestone Roll-ups
* **Spec Pointer:** [CP-103.2]
* **Affected Files:** `backend/context/manager.py`, `backend/context/compactor.py`, `backend/tests/test_context_engine.py`
* **Problem:** Inter-turn compaction currently deletes all tool results, causing the model to forget why a test failed (amnesia). Intra-turn failed loops are not collapsed when a step succeeds.
* **Target:**
  1. Retain non-zero exit codes, stderr outputs, and lint errors in compacted turn summaries.
  2. Implement Milestone Roll-up: collapse intermediate failed tool loops into a single success summary once an edit/test passes.
  3. Update `ContextCompactor` to preserve cumulative user requirements across all turns.
* **Verification:** Test verifying an error in Turn 1 is remembered in Turn 2, and failed attempt loops are compacted on milestone success.

---

### ITEM-13: Real-Time Context Telemetry & UI Gauge
* **Spec Pointer:** [CP-106]
* **Affected Files:** `backend/plugins/coding_harness.py`, `backend/engine.py`, `frontend/src/components/ChatMessage.jsx`, `frontend/src/components/LlmDebugModal.jsx`
* **Problem:** Zero visibility into active context window utilization, RAM percentage, or compaction events.
* **Target:** Emit `context_telemetry` WebSocket events with token counts, virtual RAM usage, window %, and compaction flags; display a color-coded gauge in the UI header and debug modal.
* **Verification:** End-to-end event verification ensuring UI receives accurate context telemetry payloads.

---

## 3. Phased Execution Sequence

We will tackle the 13 items in 4 logical phases:

- **Phase 1: Critical Infrastructure & Accounting** (Items 1, 2, 3)
- **Phase 2: Tool Execution, Range Bounds & Topology** (Items 4, 5, 6)
- **Phase 3: Dynamic Virtual RAM & AST Code Mapping** (Items 7, 8, 9, 10)
- **Phase 4: Rolling Lifecycle, Compaction & Telemetry** (Items 11, 12, 13)
