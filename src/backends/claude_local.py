"""Card generation via the Claude Agent SDK, authenticated through your
local Claude Code login (subscription, not a metered API key). Used for
local development. Selected by CARD_BACKEND=claude, the default (see
backends/__init__.py)."""

import asyncio
import json
import re

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from pydantic import ValidationError

from prompt import SYSTEM, CardFields

MODEL = "sonnet"

# The Agent SDK has no server-enforced structured output (unlike the
# Gemini backend's response_json_schema), so we ask for it in prose and
# parse tolerantly below.
_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a single JSON object matching this schema, and "
    "nothing else -- no markdown code fences, no explanation, no preamble "
    "or follow-up text:\n" + json.dumps(CardFields.model_json_schema())
)


def _extract_json_object(text: str) -> str:
    """Pull the outermost {...} out of a response, tolerating Markdown
    code fences or stray commentary around it."""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in Claude's response: {text!r}")
    return text[start : end + 1]


async def _run_query(vocab: str, research: bool, guidance: str = "") -> str:
    prompt = vocab
    if guidance:
        prompt = f"{prompt}\n\nAdditional guidance from the user for this card: {guidance}"

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM + _JSON_INSTRUCTION,
        model=MODEL,
        # Tools are locked down so the app can never touch the local
        # filesystem: nothing is pre-approved except WebSearch when
        # researching, and "dontAsk" denies anything else outright
        # instead of hanging on an interactive prompt that has no one to
        # answer it from inside a web request.
        allowed_tools=["WebSearch"] if research else [],
        permission_mode="dontAsk",
        # 1 turn is occasionally too tight even with no tools involved --
        # observed a real, intermittent error_max_turns failure in
        # verification testing -- so non-research gets one turn of
        # headroom rather than a hard single-shot budget.
        max_turns=3 if research else 2,
    )

    # Explicitly aclose() the generator in a finally block rather than
    # just `async for ... return`-ing out of it: returning early leaves
    # the SDK's underlying generator (and the `claude` subprocess it
    # manages) undrained, and asyncio.run()'s implicit
    # loop.shutdown_asyncgens() cleanup then races it, printing a
    # spurious "aclose(): asynchronous generator is already running"
    # RuntimeError to stderr on every call. Closing it ourselves, before
    # the loop starts tearing down, avoids that race.
    agen = query(prompt=prompt, options=options)
    try:
        async for message in agen:
            if isinstance(message, ResultMessage):
                if message.subtype != "success" or not message.result:
                    raise RuntimeError(
                        f"Claude query for {vocab!r} did not complete "
                        f"(subtype={message.subtype!r}, terminal_reason={message.terminal_reason!r})"
                    )
                return message.result
    finally:
        await agen.aclose()

    raise RuntimeError(f"Claude query for {vocab!r} produced no result message")


def generate(vocab: str, research: bool, guidance: str = "") -> CardFields:
    last_error: Exception = RuntimeError("unreachable")
    for _ in range(2):
        raw = asyncio.run(_run_query(vocab, research, guidance))
        try:
            return CardFields.model_validate_json(_extract_json_object(raw))
        except (ValueError, ValidationError) as exc:
            last_error = exc
    raise last_error
