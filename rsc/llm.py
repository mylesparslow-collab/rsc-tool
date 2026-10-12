"""Talks to the local model through Ollama's HTTP API. No email text leaves the computer."""
import base64
import json
import urllib.error
import urllib.request
from typing import Protocol


class Model(Protocol):
    def extract(self, system: str, user: str, schema: dict, images: list[bytes] | None = None) -> dict: ...


class ModelUnavailable(RuntimeError):
    pass


class OllamaModel:
    def __init__(self, url: str, name: str, timeout: int = 180):
        self.url, self.name, self.timeout = url.rstrip("/"), name, timeout

    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(f"{self.url}{path}", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.URLError as exc:
            raise ModelUnavailable(f"Can't reach Ollama at {self.url}. Is the Ollama app running? ({exc})") from exc

    def check(self) -> None:
        req = urllib.request.Request(f"{self.url}/api/tags")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                tags = json.loads(resp.read())
        except urllib.error.URLError as exc:
            raise ModelUnavailable(f"Can't reach Ollama at {self.url}. Is the Ollama app running?") from exc
        names = {m.get("name") for m in tags.get("models", [])}
        if self.name not in names and f"{self.name}:latest" not in names:
            raise ModelUnavailable(f"Model {self.name} isn't downloaded. Run: ollama pull {self.name}")

    def extract(self, system: str, user: str, schema: dict, images: list[bytes] | None = None) -> dict:
        message = {"role": "user", "content": user}
        if images:  # photos go to the model as base64, for vision models
            message["images"] = [base64.b64encode(i).decode() for i in images]
        result = self._post("/api/chat", {
            "model": self.name,
            "messages": [{"role": "system", "content": system}, message],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0},
        })
        content = result.get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model returned something that isn't JSON: {content[:200]}") from exc
