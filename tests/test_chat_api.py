import sys
from pathlib import Path

from fastapi.testclient import TestClient


CODE_DIR = Path(__file__).resolve().parents[1] / "style_imitation_code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from main import app  # noqa: E402
from api import routecore  # noqa: E402


client = TestClient(app)


class _FakeUsage:
    prompt_tokens = 12
    completion_tokens = 34


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeChunk:
    def __init__(self, content=None, usage=None):
        self.choices = [_FakeChoice(content)] if content is not None else []
        self.usage = usage


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeCompletions:
    async def create(self, **kwargs):
        return _FakeStream(
            [
                _FakeChunk("Hello "),
                _FakeChunk("world"),
                _FakeChunk(usage=_FakeUsage()),
            ]
        )


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeAsyncOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = _FakeChat()


def test_chat_rejects_empty_messages():
    response = client.post(
        "/api/chat",
        json={
            "api_key": "test-key",
            "model": "deepseek-chat",
            "messages": [],
        },
    )

    assert response.status_code == 422


def test_chat_rejects_out_of_range_temperature():
    response = client.post(
        "/api/chat",
        json={
            "api_key": "test-key",
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 3,
        },
    )

    assert response.status_code == 422


def test_chat_rejects_blank_message_content():
    response = client.post(
        "/api/chat",
        json={
            "api_key": "test-key",
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "   "}],
        },
    )

    assert response.status_code == 422


def test_chat_stream_returns_text_and_usage(monkeypatch):
    monkeypatch.setattr(routecore, "AsyncOpenAI", _FakeAsyncOpenAI)

    response = client.post(
        "/api/chat",
        json={
            "api_key": "test-key",
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "hello"}],
            "system_prompt": "You are helpful.",
            "temperature": 0.5,
            "top_p": 1.0,
        },
    )

    assert response.status_code == 200
    assert "Hello world" in response.text
    assert "__USAGE__:12,34__" in response.text
