"""Tests for the shared Bedrock helpers."""

import io
import json

import pytest

from common.llm import LLMResponseError, clamp_confidence, invoke_claude, parse_json_object

FENCE = "`" * 3


def bedrock_reply(text: str, stop_reason: str = "end_turn") -> dict:
    payload = {
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    return {"body": io.BytesIO(json.dumps(payload).encode())}


@pytest.fixture
def bedrock(mocker):
    client = mocker.Mock()
    mocker.patch("common.llm.get_bedrock_client", return_value=client)
    return client


class TestInvokeClaude:
    def test_sends_messages_request_and_returns_text(self, bedrock):
        bedrock.invoke_model.return_value = bedrock_reply('{"ok": true}')

        text = invoke_claude("model-x", "hello", system="be brief", max_tokens=100)

        assert text == '{"ok": true}'
        kwargs = bedrock.invoke_model.call_args.kwargs
        assert kwargs["modelId"] == "model-x"
        body = json.loads(kwargs["body"])
        assert body["anthropic_version"] == "bedrock-2023-05-31"
        assert body["max_tokens"] == 100
        assert "temperature" not in body
        assert body["system"] == "be brief"
        assert body["messages"] == [{"role": "user", "content": "hello"}]

    def test_cut_off_reply_raises(self, bedrock):
        bedrock.invoke_model.return_value = bedrock_reply('{"partial": ', stop_reason="max_tokens")

        with pytest.raises(LLMResponseError):
            invoke_claude("model-x", "hello")


class TestParseJsonObject:
    def test_plain_json(self):
        assert parse_json_object('{"a": 1}') == {"a": 1}

    def test_strips_code_fences(self):
        assert parse_json_object(f'{FENCE}json\n{{"a": 1}}\n{FENCE}') == {"a": 1}

    def test_finds_json_inside_a_sentence(self):
        assert parse_json_object('Here you go: {"a": 1} Hope that helps.') == {"a": 1}

    def test_reply_without_json_raises(self):
        with pytest.raises(LLMResponseError):
            parse_json_object("I could not classify this.")

    def test_json_that_is_not_an_object_raises(self):
        with pytest.raises(LLMResponseError):
            parse_json_object("[1, 2, 3]")


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.8, 0.8), ("0.5", 0.5), (1.7, 1.0), (-2, 0.0), (None, 0.0), ("high", 0.0), (float("nan"), 0.0)],
)
def test_clamp_confidence(value, expected):
    assert clamp_confidence(value) == expected
