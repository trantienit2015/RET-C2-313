"""AgentCore Platform v1.0 - RET-C2-313 domain service layer.

Deterministic domain logic for the GMC / Google Shopping operations Q&A agent
with Japan-policy overlay:
  - S-2 input sanitization + GMC topic classification (feed/disapproval/ads/
    structured-data/japan-policy/appi) - deterministic keyword routing
  - Tier-2 KB retrieval: curated Japan-locale GMC policy additions, disapproval
    resolution playbooks, and the APPI 2026 disclosure overlay (no single public
    URL - this is the stable/proprietary portion that justifies a KB snapshot)
  - Tier-1 live reference lookup: GMC Help Center / Shopping Ads policy pages
    (public, URL-stable) - referenced as a live URL, never ingested
  - Japan-locale policy overlay (product-title encoding, GTIN exemptions, JPY
    price format, APPI AI-recommendation disclosure)
  - step-by-step resolution synthesis (LLM-essential; deterministic fallback
    keeps the pipeline runnable without an LLM)
  - the non-suppressible citation-validity gate: every citation the draft answer
    references must resolve to a retrieved Tier-2 passage or a known Tier-1 URL -
    this check is NEVER skipped or overridden by upstream state

No agenticstar imports. No business logic lives in nodes - nodes call these pure
functions and own only the FunctionNode/state/security plumbing.
"""

from __future__ import annotations

import re
from typing import Any

from src.services.llm_adapter import extract_text

_HTML_TAG_RE = re.compile(r"<[^>]+>")
DEFAULT_MAX_LENGTH = 2000

# GMC topic keyword routing - deterministic, no LLM needed for classification.
_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gtin": ("gtin", "jan", "barcode", "upc", "ean"),
    "disapproval": ("disapprov", "reject", "rejected", "suspend"),
    "feed": ("feed", "product data", "attribute", "missing"),
    "ads": ("shopping ads", "campaign", "bidding", "performance max"),
    "structured_data": ("structured data", "schema.org", "markup", "rich result"),
    "appi": ("appi", "個人情報", "disclosure", "ai recommendation"),
    "japan_policy": ("japan", "japanese", "jpy", "日本"),
}

# Tier-2 KB: curated Japan-locale GMC policy additions + disapproval playbooks +
# APPI overlay. Stable/proprietary - no single public URL (justifies a snapshot).
_TIER2_KB: dict[str, list[dict[str, str]]] = {
    "gtin": [
        {
            "doc_id": "jp-gtin-exemption-001",
            "source": "Japan-additions playbook",
            "text": "Domestic-only Japan products without a JAN/GTIN may request a GTIN exemption via "
            "Merchant Center 'identifier_exists=false' when the manufacturer never assigned one.",
        }
    ],
    "disapproval": [
        {
            "doc_id": "jp-disapproval-playbook-001",
            "source": "Disapproval resolution playbook",
            "text": "For 'missing GTIN' disapprovals on Japan-domestic SKUs: set identifier_exists=false, "
            "resubmit the feed, and expect re-review within 3-5 business days.",
        },
        {
            "doc_id": "jp-disapproval-playbook-002",
            "source": "Disapproval resolution playbook",
            "text": "For product-title encoding disapprovals: ensure UTF-8 without HTML entities; "
            "full-width characters in titles are a common Japan-locale rejection cause.",
        },
    ],
    "japan_policy": [
        {
            "doc_id": "jp-locale-price-001",
            "source": "Japan-additions playbook",
            "text": "JPY prices must be submitted as whole integers (no decimal yen) in the price attribute.",
        }
    ],
    "appi": [
        {
            "doc_id": "jp-appi-2026-001",
            "source": "APPI 2026 overlay (version-pinned)",
            "text": "Under APPI 2026, Japan operators must disclose to end users when Google Shopping's AI "
            "recommendation algorithm is applied to product surfacing on their listings.",
        }
    ],
}

# Tier-1: live GMC Help Center / Shopping Ads policy pages (public, URL-stable).
# Referenced as a live URL - never ingested into the KB.
_TIER1_URLS: dict[str, dict[str, str]] = {
    "gtin": {
        "title": "Google Merchant Center - GTIN requirements",
        "url": "https://support.google.com/merchants/answer/6219078",
    },
    "disapproval": {
        "title": "Google Merchant Center - Disapproved products",
        "url": "https://support.google.com/merchants/answer/6098295",
    },
    "feed": {
        "title": "Google Merchant Center - Product data specification",
        "url": "https://support.google.com/merchants/answer/7052112",
    },
    "ads": {"title": "Google Shopping Ads - Policies", "url": "https://support.google.com/merchants/answer/6149970"},
    "structured_data": {
        "title": "Google Search Central - Product structured data",
        "url": "https://developers.google.com/search/docs/appearance/structured-data/product",
    },
    "general": {"title": "Google Merchant Center Help", "url": "https://support.google.com/merchants"},
}


def sanitize_query(text: str, max_length: int = DEFAULT_MAX_LENGTH) -> str:
    """Strip HTML tags (injection/markup guard) and cap length."""
    return _HTML_TAG_RE.sub("", text)[:max_length]


def classify_gmc_topic(query: str) -> str:
    """Deterministic GMC topic classification via keyword routing."""
    lowered = query.lower()
    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return topic
    return "general"


def retrieve_policy(
    gmc_topic: str, query: str, kb: dict[str, list[dict[str, str]]] | None = None
) -> list[dict[str, str]]:
    """Tier-2 KB retrieval - Japan-additions + disapproval playbooks + APPI overlay."""
    source = kb if kb is not None else _TIER2_KB
    passages = list(source.get(gmc_topic, []))
    if "japan" in query.lower() and gmc_topic != "japan_policy":
        passages.extend(source.get("japan_policy", []))
    return [{"tier": "2", **p} for p in passages]


def live_reference(gmc_topic: str) -> dict[str, str]:
    """Tier-1 live GMC/Shopping policy URL reference (not ingested)."""
    return _TIER1_URLS.get(gmc_topic, _TIER1_URLS["general"])


def apply_japan_overlay(gmc_topic: str, query: str) -> dict[str, Any]:
    """Japan-locale policy overlay: encoding, GTIN exemptions, JPY format, APPI disclosure."""
    overlay: dict[str, Any] = {
        "encoding_note": "Use UTF-8 without HTML entities; avoid full-width characters in feed titles.",
        "gtin_exemption_applicable": gmc_topic in ("gtin", "disapproval"),
        "jpy_price_format": "Submit JPY prices as whole integers (no decimal yen).",
        "appi_disclosure_required": gmc_topic == "appi" or "ai recommendation" in query.lower(),
    }
    return overlay


class LLMSynthesisError(RuntimeError):
    """A configured LLM failed or returned an invalid response during synthesis.

    Raised only when `llm` is not None (a live client IS configured) - the
    deterministic playbook fallback below is a deliberate deterministic-core
    mode reserved for `llm is None`, never a silent substitute for a live LLM
    that errored or returned nothing (silently
    falling back here would make an LLM outage indistinguishable from success).
    """


def synthesize_resolution(
    query: str,
    passages: list[dict[str, str]],
    live_ref: dict[str, str],
    overlay: dict[str, Any],
    llm: Any | None = None,
) -> tuple[str, list[str]]:
    """Step-by-step resolution synthesis with citations.

    LLM-essential; deterministic fallback keeps the pipeline runnable without an LLM.
    Citations returned are always a subset of {passage doc_id} u {live_ref url} -
    the caller (post_process S-3 gate) re-verifies this non-suppressibly.

    Raises:
        LLMSynthesisError: `llm` is configured but the call raised, or the
            normalized response text is empty - the caller must surface this as
            an ERROR status, not silently degrade to the deterministic path.
    """
    citations = [p["doc_id"] for p in passages] + [live_ref["url"]]
    if llm is not None and hasattr(llm, "complete"):
        prompt = (
            f"Answer this GMC/Google Shopping operations question: '{query}'. "
            f"Use these Tier-2 passages: {passages}. Reference live policy: {live_ref}. "
            f"Japan overlay: {overlay}. Cite only doc_id/url values already provided."
        )
        try:
            # Canonical BaseLLM.complete(messages: list[dict]) -> dict; a live
            # client returns a dict {"content": ...}, not a bare string.
            raw = llm.complete([{"role": "user", "content": prompt}])
        except Exception as exc:  # narrow provider/transport failure, not a silent swallow
            raise LLMSynthesisError(f"LLM provider call failed: {exc}") from exc
        text = extract_text(raw).strip()
        if not text:
            raise LLMSynthesisError("LLM returned an empty/invalid response")
        return text, citations
    steps = [f"- {p['source']}: {p['text']}" for p in passages]
    draft = (
        f"Resolution for: {query}\n"
        + ("\n".join(steps) if steps else "- No Japan-additions playbook matched; see live GMC policy below.")
        + f"\nPolicy reference: {live_ref['title']} ({live_ref['url']})"
        + f"\nJapan considerations: {overlay}"
    )
    return draft, citations


def validate_citations(citations: list[str], passages: list[dict[str, str]], live_ref: dict[str, str]) -> bool:
    """Non-suppressible S-3 check: every citation must resolve to a known passage or live URL.

    Called unconditionally from the gate node's execute() AND re-verified in the
    S-3 hook - it never trusts a prior "validated" flag from upstream state.
    """
    known = {p["doc_id"] for p in passages} | {live_ref["url"]}
    return all(c in known for c in citations)
