import json

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage

from backends import claude_local
from prompt import CardFields

CARD_JSON = json.dumps(
    {
        "front": "es wird bald Winter",
        "expression": "もうすぐ冬になる",
        "reading": "もうすぐ 冬[ふゆ]になる",
        "bemerkungen": "",
    }
)


def make_result(result=None, subtype="success", terminal_reason="end_turn"):
    """A real ResultMessage instance with only the fields claude_local.py
    actually reads set -- built via __new__ to skip the real dataclass's
    other (unrelated, and largely unknown-to-us) required constructor
    args. Must be a genuine ResultMessage: production code does
    isinstance(message, ResultMessage), and an earlier version of this
    test file used a duck-typed stand-in with a hand-added `.type =
    "result"` attribute that matched an earlier (wrong) duck-typing
    check in the production code -- the tests all passed while the real
    check against actual SDK objects was broken, because the fake
    invented the exact attribute the wrong assumption needed. See the
    debug session that found this: claude_agent_sdk's real message
    classes have no `.type` attribute at all."""
    obj = ResultMessage.__new__(ResultMessage)
    obj.result = result
    obj.subtype = subtype
    obj.terminal_reason = terminal_reason
    return obj


def make_other_message():
    """A real non-ResultMessage message (e.g. what an AssistantMessage
    looks like to isinstance), which the loop should skip over on its
    way to the ResultMessage."""
    return AssistantMessage.__new__(AssistantMessage)


def _fake_query(*messages):
    """Build a fake replacement for claude_agent_sdk.query() that yields
    the given messages and records the prompt/options it was called
    with."""
    calls = []

    async def fake(*, prompt, options):
        calls.append({"prompt": prompt, "options": options})
        for m in messages:
            yield m

    fake.calls = calls
    return fake


def test_generate_parses_the_result_message(monkeypatch):
    fake = _fake_query(make_other_message(), make_result(result=CARD_JSON))
    monkeypatch.setattr(claude_local, "query", fake)

    card = claude_local.generate("Xになる", research=False)

    assert card == CardFields.model_validate_json(CARD_JSON)
    assert fake.calls[0]["prompt"] == "Xになる"


def test_generate_strips_markdown_code_fences(monkeypatch):
    fenced = f"```json\n{CARD_JSON}\n```"
    fake = _fake_query(make_result(result=fenced))
    monkeypatch.setattr(claude_local, "query", fake)

    card = claude_local.generate("Xになる", research=False)

    assert card == CardFields.model_validate_json(CARD_JSON)


def test_generate_strips_surrounding_commentary(monkeypatch):
    chatty = f"Sure, here's the card:\n{CARD_JSON}\nLet me know if you need changes!"
    fake = _fake_query(make_result(result=chatty))
    monkeypatch.setattr(claude_local, "query", fake)

    card = claude_local.generate("Xになる", research=False)

    assert card == CardFields.model_validate_json(CARD_JSON)


def test_generate_retries_once_after_a_parse_failure(monkeypatch):
    # generate()'s retry loop calls query() fresh each attempt (a new
    # asyncio.run(_run_query(...)) per iteration) rather than resuming one
    # generator, so the response-per-attempt selection has to key off how
    # many times the fake was *invoked*, not off resuming after a yield.
    responses = [make_result(result="not json at all"), make_result(result=CARD_JSON)]
    call_count = 0

    async def fake(*, prompt, options):
        nonlocal call_count
        response = responses[call_count]
        call_count += 1
        yield response

    monkeypatch.setattr(claude_local, "query", fake)

    card = claude_local.generate("Xになる", research=False)

    assert card == CardFields.model_validate_json(CARD_JSON)
    assert call_count == 2


def test_generate_raises_after_two_failed_parses(monkeypatch):
    async def always_bad(*, prompt, options):
        yield make_result(result="still not json")

    monkeypatch.setattr(claude_local, "query", always_bad)

    with pytest.raises(ValueError, match="no JSON object"):
        claude_local.generate("Xになる", research=False)


def test_generate_raises_on_unsuccessful_result(monkeypatch):
    fake = _fake_query(make_result(result=None, subtype="error", terminal_reason="aborted_tools"))
    monkeypatch.setattr(claude_local, "query", fake)

    with pytest.raises(RuntimeError, match="did not complete"):
        claude_local.generate("Xになる", research=False)


def test_generate_raises_if_no_result_message_ever_arrives(monkeypatch):
    fake = _fake_query(make_other_message(), make_other_message())
    monkeypatch.setattr(claude_local, "query", fake)

    with pytest.raises(RuntimeError, match="no result message"):
        claude_local.generate("Xになる", research=False)


def test_non_research_mode_locks_tools_down_to_nothing(monkeypatch):
    fake = _fake_query(make_result(result=CARD_JSON))
    monkeypatch.setattr(claude_local, "query", fake)

    claude_local.generate("Xになる", research=False)

    options = fake.calls[0]["options"]
    assert options.allowed_tools == []
    assert options.permission_mode == "dontAsk"
    assert options.max_turns == 2


def test_research_mode_pre_approves_only_web_search(monkeypatch):
    fake = _fake_query(make_result(result=CARD_JSON))
    monkeypatch.setattr(claude_local, "query", fake)

    claude_local.generate("Xになる", research=True)

    options = fake.calls[0]["options"]
    assert options.allowed_tools == ["WebSearch"]
    assert options.permission_mode == "dontAsk"
    assert options.max_turns == 3
