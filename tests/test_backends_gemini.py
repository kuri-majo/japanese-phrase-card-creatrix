import json
from unittest.mock import MagicMock

import pytest
from google.genai import types

from backends import gemini
from prompt import CardFields

CARD_JSON = json.dumps(
    {
        "front": "es wird bald Winter",
        "expression": "もうすぐ冬になる",
        "reading": "もうすぐ 冬[ふゆ]になる",
        "bemerkungen": "",
    }
)


@pytest.fixture(autouse=True)
def _reset_client_singleton(monkeypatch):
    # _get_client() memoizes into the module-level _client global; make
    # sure one test's mock client can't leak into the next.
    monkeypatch.setattr(gemini, "_client", None)


def test_generate_without_research_makes_one_structured_call(monkeypatch):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(text=CARD_JSON)
    monkeypatch.setattr(gemini, "_get_client", lambda: mock_client)

    card = gemini.generate("Xになる", research=False)

    assert card == CardFields.model_validate_json(CARD_JSON)
    assert mock_client.models.generate_content.call_count == 1

    _, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["model"] == gemini.MODEL
    assert kwargs["contents"] == "Xになる"  # no research findings prepended
    config = kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == CardFields.model_json_schema()
    assert config.system_instruction == gemini.SYSTEM


def test_generate_with_research_makes_a_grounded_call_then_a_structured_one(monkeypatch):
    mock_client = MagicMock()
    findings_response = MagicMock(text="Found: もうすぐ冬になる in a weather forecast.")
    card_response = MagicMock(text=CARD_JSON)
    mock_client.models.generate_content.side_effect = [findings_response, card_response]
    monkeypatch.setattr(gemini, "_get_client", lambda: mock_client)

    card = gemini.generate("Xになる", research=True)

    assert card == CardFields.model_validate_json(CARD_JSON)
    assert mock_client.models.generate_content.call_count == 2

    first_kwargs = mock_client.models.generate_content.call_args_list[0].kwargs
    first_config = first_kwargs["config"]
    assert first_config.tools is not None
    assert isinstance(first_config.tools[0], types.Tool)
    assert first_config.tools[0].google_search is not None
    # The research call must NOT also ask for structured JSON output —
    # grounding and response_json_schema aren't combined on one call.
    assert first_config.response_json_schema is None

    second_kwargs = mock_client.models.generate_content.call_args_list[1].kwargs
    assert "Xになる" in second_kwargs["contents"]
    assert "weather forecast" in second_kwargs["contents"]
    assert second_kwargs["config"].response_json_schema == CardFields.model_json_schema()


def test_generate_raises_a_clear_error_on_empty_response(monkeypatch):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(text=None)
    monkeypatch.setattr(gemini, "_get_client", lambda: mock_client)

    with pytest.raises(RuntimeError, match="Xになる"):
        gemini.generate("Xになる", research=False)


def test_get_client_constructs_only_once(monkeypatch):
    # _get_client() memoizes into the module-level _client global, so a
    # second call reuses the same instance instead of re-authenticating.
    made = []
    monkeypatch.setattr(gemini.genai, "Client", lambda: made.append(object()) or made[-1])

    first = gemini._get_client()
    second = gemini._get_client()

    assert first is second
    assert len(made) == 1
