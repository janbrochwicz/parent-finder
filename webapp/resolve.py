"""Resolve a single company's parent/owning company via Claude + web search."""
import json

from lib import no_parent_evidence, normalize_domain

MODEL = "claude-haiku-4-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "parent_name": {
            "type": "string",
            "description": "Name of the parent/owning company. Leave empty if the company has no parent.",
        },
        "parent_domain": {
            "type": "string",
            "description": "Domain of the parent/owning company. Leave empty if the company has no parent.",
        },
        "verified": {"type": "string", "enum": ["Yes", "No", "Maybe"]},
        "evidence": {
            "type": "string",
            "description": "One-line justification citing what was found",
        },
    },
    "required": ["parent_name", "parent_domain", "verified", "evidence"],
    "additionalProperties": False,
}

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
"""


def resolve_company(client, name, domain):
    """Look up one company's parent via Claude + web search. Returns a dict matching SCHEMA."""
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

    kwargs = dict(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        tools=tools,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )

    response = client.messages.create(messages=messages, **kwargs)

    # Server-side search hit its internal iteration cap - resend to continue, no extra prompt needed.
    if response.stop_reason == "pause_turn":
        messages.append({"role": "assistant", "content": response.content})
        response = client.messages.create(messages=messages, **kwargs)

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return {"parent_name": "", "parent_domain": "", "verified": "No", "evidence": "No response from model"}
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return {
            "parent_name": "",
            "parent_domain": "",
            "verified": "No",
            "evidence": f"Could not parse model output: {text[:200]}",
        }

    # Guardrail: never let the parent domain equal the company's own domain, regardless of
    # what the model returned - that's not a parent, it's the same company (see prompt point 3).
    if normalize_domain(result.get("parent_domain", "")) == domain:
        result["parent_name"] = ""
        result["parent_domain"] = ""
        result["verified"] = "No"
        result["evidence"] = no_parent_evidence(name, result.get("evidence", ""))

    return result
