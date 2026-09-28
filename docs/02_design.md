# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `RetailGmcOperationsQAGraph` (outer, `src/graph/graph.py`)
- **L1 Base**: `AgentBaseGraph` (L1 direct) — Cat 2 composition: outer backbone +
  `GraphNode` in the `main` slot wrapping an inner `BaseGraph` (`GmcOperationsWorkflowGraph`).
  `VectorRAGAgent` is a pattern reference only (no L2 inheritance).
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible); nested
    list/dict fields stored as JSON strings (`to_json`/`from_json`)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (outer `register_nodes()` for the 3 domain slots; inner
    `register_nodes()`/`add_edges()` for the 4-step workflow topology)

## Architecture Overview

### Node Configuration (outer)

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | — | — | InitializeNode (default) |
| pre_process | `InputValidateNode` — S-1/S-2 sanitize + GMC topic classify | `user_input` | `gmc_topic`, `validated_input` | FunctionNode |
| main | `GmcOperationsGraphNode` — dispatch to inner workflow | `validated_input` | `gmc_topic`, `retrieved_passages`, `live_refs`, `japan_overlay`, `draft_answer`, `citations` | GraphNode (wraps inner `BaseGraph`) |
| post_process | `ResponseValidateNode` — S-3 non-suppressible citation gate + answer assembly | draft_answer, citations, retrieved_passages, live_refs | `formatted_output` | FunctionNode |
| finalize | response_metadata, total_time_ms | — | — | FinalizeNode (default) |

### Node Configuration (inner — `GmcOperationsWorkflowGraph`, `src/graph/domain_workflow_graph.py`)

| Inner node | Responsibility | Output |
|---|---|---|
| `intent_classify` | Classify query into GMC sub-domain (feed/disapproval/ads/structured-data/japan-policy/appi) for KB routing | `intent`, `gmc_topic` |
| `policy_retrieve` | Tier-2 KB retrieval (Japan-locale GMC policy additions, disapproval playbooks, APPI overlay) + Tier-1 live GMC/Shopping URL reference | `retrieved_passages`, `live_refs` |
| `japan_policy_filter` | Japan-locale overlay: title encoding, GTIN exemptions, JPY price format, APPI disclosure | `japan_overlay` |
| `resolution_synthesize` | LLM-essential step-by-step resolution + citations (deterministic fallback) | `draft_answer`, `citations` |

### Data Flow

```
START → initialize → pre_process(InputValidate) → main(GraphNode) → post_process(ResponseValidate) → finalize → END
                                                        │
                                                        ▼ (extract_input: validated_input JSON string)
                                    INNER: intent_classify → policy_retrieve → japan_policy_filter → resolution_synthesize
                                                        │
                                                        ▼ (merge_output: gmc_topic/passages/refs/overlay/answer/citations)
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `gmc_topic` | `NotRequired[str]` | Classified GMC sub-domain (feed/disapproval/ads/structured_data/japan_policy/appi/general) | No |
| `retrieved_passages` | `NotRequired[str \| None]` (JSON list[dict]) | Tier-2 KB retrieval results (doc_id/tier/source/text) | No |
| `live_refs` | `NotRequired[str \| None]` (JSON list[dict]) | Tier-1 live GMC/Shopping URL references (not ingested) | No |
| `japan_overlay` | `NotRequired[str \| None]` (JSON dict) | Japan-locale policy overlay (encoding, GTIN exemption, JPY format, APPI disclosure) | No |
| `draft_answer` | `NotRequired[str \| None]` | Synthesized step-by-step resolution before S-3 validation | No |
| `citations` | `NotRequired[str \| None]` (JSON list[str]) | Citation doc_ids/URLs the draft answer references | No |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types) — nested containers stored as JSON strings
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [ ] ConnectionPolicy (retry/timeout strategy) — not used; deterministic KB, no external network I/O
- [x] SecurityViolationError (framework-enforced at S-1/S-2/S-3 gates)
- [x] S-2: `_extra_security_gate_input()` on `InputValidateNode` — input length cap re-check at the gate boundary
- [x] S-3: `_extra_security_gate_output()` on `ResponseValidateNode` — non-suppressible re-check that
      every citation resolves to a retrieved Tier-2 passage or the Tier-1 live URL; rejects fabricated
      GMC policy citations even if `status`/`formatted_output` was tampered with upstream
- [x] S-4: `emit_trace_event()` — at least one domain-specific event inside every node's `execute()`
      (`InputValidateNode`, all 4 inner nodes, `ResponseValidateNode`), plus the `GraphNode` wrapper
      emits dispatch/completion events from `extract_input()`/`merge_output()`

### Composition Pattern

- **Pattern**: Cat 2 — outer `AgentBaseGraph` + `GraphNode` (`main` slot) wrapping inner `BaseGraph`
- **Composition target**: `GmcOperationsWorkflowGraph` (`src/graph/domain_workflow_graph.py`)
- **Error propagation strategy**: `propagate` (fail fast — inner `ERROR` status short-circuits via
  conditional edges to `END`; `GraphNode.error_strategy = "propagate"` re-raises inner exceptions as
  `SubgraphError`)

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | **AgentBaseGraph** | Fixed multi-step workflow, no autonomous think-act loop needed |
| Composition pattern | Flat Cat 1-style MainNode | GraphNode + inner BaseGraph | **GraphNode + inner BaseGraph** | Cat 2 requirement (`gate-composition`) — 4 business steps, use-case-specific workflow |
| KB architecture | Full snapshot of GMC Help Center | Two-tier: live-fetch (public) + snapshot (Japan-specific proprietary) | **Two-tier** | Public GMC docs are URL-stable and Google-updated — a snapshot would go stale; only the Japan-locale additions/playbooks/APPI overlay have no single public URL and justify a curated KB |
