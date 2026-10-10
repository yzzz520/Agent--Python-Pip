"""Minimal OpenAI-compatible chat client.

Reads configuration from environment variables first, then from the local
.env file. The API key is never printed or written to logs.
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


class LLMConfigError(RuntimeError):
    pass


def load_env_file(path=ENV_PATH):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def get_config():
    file_values = load_env_file()

    def pick(name, default=None):
        return os.environ.get(name) or file_values.get(name) or default

    base_url = pick("LLM_BASE_URL")
    api_key = pick("LLM_API_KEY")
    model = pick("LLM_MODEL")

    missing = [
        name
        for name, value in (
            ("LLM_BASE_URL", base_url),
            ("LLM_API_KEY", api_key),
            ("LLM_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise LLMConfigError(f"缺少配置: {', '.join(missing)} (检查 .env 或环境变量)")

    return base_url.rstrip("/"), api_key, model


class LLMClient:
    def __init__(self, base_url=None, api_key=None, model=None, timeout=180):
        env_base_url, env_api_key, env_model = get_config()
        self.base_url = (base_url or env_base_url).rstrip("/")
        self.api_key = api_key or env_api_key
        self.model = model or env_model
        self.timeout = timeout

    def chat(self, messages, temperature=0.0, max_tokens=1200, json_mode=True, retries=2):
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "codex-llm-analyzer/1.0",
            },
        )

        last_error = None
        for attempt in range(retries + 1):
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                latency_ms = int((time.perf_counter() - started) * 1000)
                choice = payload["choices"][0]
                message = choice["message"]
                return {
                    "content": message.get("content") or "",
                    "reasoning_content": message.get("reasoning_content") or "",
                    "finish_reason": choice.get("finish_reason"),
                    "usage": payload.get("usage", {}),
                    "latency_ms": latency_ms,
                    "model": payload.get("model", self.model),
                }
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                last_error = RuntimeError(f"LLM API HTTP {exc.code}: {detail}")
                if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = RuntimeError(f"LLM API connection error: {exc.reason}")
                if attempt < retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last_error from exc

        raise last_error or RuntimeError("LLM request failed")

    def chat_with_tools(self, messages, tools, temperature=0.0, max_tokens=2000, retries=2):
        """OpenAI-compatible tool calling. Returns the full assistant message."""
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": tools,
            "tool_choice": "auto",
        }
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "codex-agent-analyzer/1.0",
            },
        )

        last_error = None
        for attempt in range(retries + 1):
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                latency_ms = int((time.perf_counter() - started) * 1000)
                choice = payload["choices"][0]
                message = choice["message"]
                return {
                    "message": message,
                    "content": message.get("content") or "",
                    "tool_calls": message.get("tool_calls") or [],
                    "finish_reason": choice.get("finish_reason"),
                    "usage": payload.get("usage", {}),
                    "latency_ms": latency_ms,
                    "model": payload.get("model", self.model),
                }
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                last_error = RuntimeError(f"LLM API HTTP {exc.code}: {detail}")
                if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = RuntimeError(f"LLM API connection error: {exc.reason}")
                if attempt < retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last_error from exc

        raise last_error or RuntimeError("LLM tool request failed")
