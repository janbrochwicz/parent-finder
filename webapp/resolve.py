"""Resolve a single company's parent/owning company via Claude + web search."""
import json
import re

from lib import no_parent_evidence, normalize_domain

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """You identify the parent/owning company for a given company, using web search.

For the company you're given:
1. Search for evidence of acquisition, ownership, or subsidiary status (e.g. "<company>" acquired by,
   "<company>" parent company, "<company>" subsidiary of).
2. Decide verified:
   - "Yes": found a specific, citable acquisition/ownership fact (who bought it, when, or an explicit
     "X is a subsidiary of Y" statement). Fill in parent_name/parent_domain.
   - "Maybe": plausible connection but no solid citation. Fill in parent_name/parent_domain with the
     best candidate.
   - "No": no evidence of any parent - the company is independently owned/operated, or search only
     surfaced unrelated/coincidental name matches. Leave parent_name and parent_domain EMPTY, and
     make evidence explicitly say no parent company was found (e.g. "No parent company found -
     <Company> operates independently.").
3. IMPORTANT: a company operating under its own legal entity name (e.g. "Acme Inc." running the
   acme.com website) is NOT a parent company - that is just the company's own legal name, not a
   separate owner. Only report a parent when it is a genuinely different company (a distinct brand
   or business that acquired, invested in, or otherwise owns this one). If the only "owner" you find
   operates the exact same website/domain as the company itself, treat this as verified="No" with
   empty parent_name/parent_domain - do not name the operating entity as the parent.
4. Write one line of evidence explaining the verdict.

When you are done researching, output ONLY a JSON object as your final message - no prose, no
markdown fences - with exactly these keys:
{"parent_name": "", "parent_domain": "", "verified": "Yes|No|Maybe", "evidence": ""}
"""

FALLBACK_KEYS = ("parent_name", "parent_domain", "verified", "evidence")


def _empty(verified, evidence):
    return {"parent_name": "", "parent_domain": "", "verified": verified, "evidence": evidence}


def _extract_json(text):
    """Pull the JSON object out of the model's text response, tolerant of stray prose/fences."""
    if not text:
        return None
    for candidate in (text.strip(), *re.findall(r"\{.*?\}", text, re.DOTALL)[::-1]):
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict) and "verified" in obj:
            return {k: (obj.get(k) or "") for k in FALLBACK_KEYS}
    return None


def resolve_company(client, name, domain):
    """Look up one company's parent via Claude + web search. Never raises - always returns a dict."""
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}]
    messages = [
        {
            "role": "user",
            "content": (
                f"Company name: {name or '(unknown)'}\n"
                f"Company domain: {domain}\n\n"
                "Find this company's parent/owning company."
            ),
        }
    ]
    kwargs = dict(model=MODEL, max_tokens=2000, system=SYSTEM_PROMPT, tools=tools)

    try:
        response = client.messages.create(messages=messages, **kwargs)
        # Server-side search can pause its internal loop; resume up to a few times.
        guard = 0
        while response.stop_reason == "pause_turn" and guard < 4:
            messages.append({"role": "assistant", "content": response.content})
            response = client.messages.create(messages=messages, **kwargs)
            guard += 1
    except Exception as e:  # bad key, rate limit, model/tool error - degrade, don't crash the upload
        return _empty("No", f"Lookup could not run ({type(e).__name__}). Check the API key and try again.")

    text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
    result = _extract_json(text)
    if result is None:
        return _empty("No", "Lookup returned no parseable result.")

    # Guardrail: never let the parent domain equal the company's own domain - that's not a parent.
    if normalize_domain(result.get("parent_domain", "")) == domain:
        result["parent_name"] = ""
        result["parent_domain"] = ""
        result["verified"] = "No"
        result["evidence"] = no_parent_evidence(name, result.get("evidence", ""))

    return result
