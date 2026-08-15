"""Card generation via Gemini on Vertex AI. Used on Cloud Run, where the
service account's Application Default Credentials authenticate the client —
no API key. Selected by CARD_BACKEND=gemini (see backends/__init__.py)."""

from google import genai
from google.genai import types

from prompt import SYSTEM, CardFields

MODEL = "gemini-3.7-flash"

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    # Constructed lazily, not at import time, so importing this module
    # doesn't require GOOGLE_GENAI_USE_ENTERPRISE / ADC to be configured
    # unless CARD_BACKEND=gemini actually selects it.
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def _research(client: genai.Client, vocab: str) -> str:
    """Ground the generation in a couple of real, attested usages before
    writing the card. Plain-text output — kept as a separate call from the
    structured generation below, since Google Search grounding and
    response_json_schema aren't combined on one call here."""
    resp = client.models.generate_content(
        model=MODEL,
        contents=(
            f'Search for how the Japanese vocabulary "{vocab}" is actually '
            "used. Briefly summarize 2-3 real, attested example sentences "
            "or phrases and what they mean."
        ),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    return resp.text or ""


def generate(vocab: str, research: bool, guidance: str = "") -> CardFields:
    client = _get_client()

    contents = vocab
    if research:
        findings = _research(client, vocab)
        if findings:
            contents = f"{contents}\n\nReal usage found via web search:\n{findings}"
    if guidance:
        contents = f"{contents}\n\nAdditional guidance from the user for this card: {guidance}"

    resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_json_schema=CardFields.model_json_schema(),
        ),
    )
    if not resp.text:
        raise RuntimeError(f"Gemini returned no content for {vocab!r} (finish_reason may indicate why)")
    return CardFields.model_validate_json(resp.text)
