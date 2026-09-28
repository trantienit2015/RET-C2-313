# Test Specification

## Test Strategy
- Coverage target: every node ≥1 unit success + ≥1 error/edge path; full graph ≥1 integration compile+invoke
- Test types: Unit (`tests/unit/test_nodes.py`) / Integration (`tests/integration/test_graph.py`) / Proof-of-Boundary (`tests/proof_of_boundary/`)

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | PASS |
| TC-02 | SecurityViolationError fires on invalid input | Error raised | PASS |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | PASS |
| TC-04 | InvocationContext via configurable only | Direct access raises error | PASS |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start`/`node_complete`/`node_error` absent from `execute()` body | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | 0 overrides |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused | PASS |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial | `InputValidateNode` length cap re-check at gate | PASS |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial | `ResponseValidateNode` non-suppressible citation re-check at gate | PASS |
| TC-11 | S-4: ≥1 domain `emit_trace_event()` inside every `execute()` | Domain event emitted on every node's invocation path | ≥1 per node |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | PASS |
| PB-2 | State serialization | Post-invoke State is primitives only (JSON-string containers) | No Pydantic/dataclass | PASS |
| PB-3 | L1 → External service | Deterministic Tier-2 KB + Tier-1 live-URL reference (no live network call in this template) | Data retrieved from curated KB | PASS |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | PASS |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | PASS |
| PB-6 | Invoke execution order | `__call__()`: S-1 → S-4 `node_start` → S-2 → `execute()` → S-3 → S-4 `node_complete` | Order verified for every `src/nodes/*` `BaseNode` subclass | PASS |
| PB-7 | HITL interrupt propagation *(conditional)* | `hitl.enabled` is not set in `config/agent.yaml` | Auto-waived — non-HITL | Auto-waived — non-HITL |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | GTIN disapproval resolution (full pipeline) | "My product feed has a missing GTIN disapproval for 200 Japan SKUs" | `gmc_topic` in {gtin, disapproval}; citations non-empty; live GMC GTIN URL referenced | PASS |
| BL-02 | APPI 2026 disclosure query | "Do I need to disclose Google Shopping AI recommendation under APPI 2026?" | `japan_overlay.appi_disclosure_required == true` | PASS |
| BL-03 | Fabricated citation rejected (S-3 non-suppressible gate) | Draft answer citing a doc_id not in retrieved passages or live URL | `status == ERROR`; `error_log` contains "S-3 gate" | PASS |
| BL-04 | Empty operator query | `""` | `status` in {error, cancelled} | PASS |

## Test Execution Summary
- Execution date: 2026-07-16
- Total tests: unit (per-node success + error/edge, 15 tests) + integration (3) + proof_of_boundary (generic, scaffold-provided)
- Pass: all / Fail: 0 / Skip: PB-7 auto-waived (non-HITL)
- Coverage: every node ≥1 success + ≥1 error/edge path; full outer+inner pipeline covered by integration tests
