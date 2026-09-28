# RET-C2-313 — Retail Google Merchant Center & Google Shopping Operations Q&A Agent

> **Category**: Cat 2 (orchestrates multiple steps to accomplish a specific use case)
> **Industry**: RET

## Overview

Answers operational questions from online retailers about Google Merchant Center and Google
Shopping (product feeds, GTIN requirements, disapproved products, Shopping ads policy, product
structured data, and Japan-specific feed rules), with Japan-market notes added to every answer.
The input is the question as plain text. An empty question is rejected; HTML tags are stripped and
the question is capped at 2,000 characters. The framework's input scan masks personal data before
the question reaches the workflow, which can also mask capitalised product names.

The agent routes the question to a topic by keyword (`general` when nothing matches), retrieves the
matching playbook passages from a small knowledge base bundled with the code (plus the Japan
passages when the question mentions Japan), picks one official Google help page for the topic, and
builds a Japan overlay (UTF-8 feed encoding, whether a GTIN exemption can apply, whole-yen price
format, whether an AI-recommendation disclosure under Japan's personal-information law is needed).
It then writes a step-by-step answer and returns it with the topic, the policy page, the overlay and
the citations. Every citation must match a retrieved passage id or the policy page URL; otherwise
the answer is rejected. The knowledge base is a static snapshot, not a live copy of Google's
policies.

A language model is optional. When one is configured it writes the answer from the passages and
overlay; a failed or empty reply ends the run with an error. Without a model the answer lists the
retrieved passages, the policy page and the overlay. The bundled HTTP entry point builds an
Anthropic client only when an `LLM_API_KEY` secret is available (the `RET_C2_313_ALLOW_STUB_LLM`
flag forces the no-model path), and requires an authenticated caller.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | 3.11 or later |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and test specification
```

See `docs/02_design.md` for the design and `docs/03_test_spec.md` for the test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
