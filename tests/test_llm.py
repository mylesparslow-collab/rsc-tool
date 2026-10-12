import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rsc.llm import ModelUnavailable, OllamaModel


@pytest.fixture
def fake_ollama():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send({"models": [{"name": "llama3.1:8b"}]})

        def do_POST(self):
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self._send({"message": {"role": "assistant", "content": '{"kind": "other", "confidence": 0.9}'}})

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", seen
    server.shutdown()


def test_request_uses_schema_and_no_randomness(fake_ollama):
    url, seen = fake_ollama
    model = OllamaModel(url, "llama3.1:8b")
    model.check()
    out = model.extract("sys", "user text", {"type": "object"})
    assert out["kind"] == "other"
    body = seen["body"]
    assert body["format"] == {"type": "object"} and body["stream"] is False
    assert body["options"]["temperature"] == 0
    assert body["messages"][1]["content"] == "user text"


def test_missing_model_is_explained(fake_ollama):
    url, _ = fake_ollama
    with pytest.raises(ModelUnavailable, match="ollama pull qwen"):
        OllamaModel(url, "qwen3:8b").check()


def test_ollama_not_running():
    with pytest.raises(ModelUnavailable, match="Is the Ollama app running"):
        OllamaModel("http://127.0.0.1:9", "x").check()
