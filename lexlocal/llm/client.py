"""Minimal Ollama client (loopback only).

- JSON-schema constrained output (Ollama `format`), temperature 0.1
- timeout, one retry on invalid JSON / schema failure, graceful LLMError
- logs model, timing and token counts only — never prompt or response text
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional, Type
from urllib.parse import urlparse

import requests
from pydantic import BaseModel, ValidationError

from lexlocal import config

log = logging.getLogger("lexlocal.llm")


class LLMError(Exception):
    pass


_stats_lock = threading.Lock()
STATS = {"calls": 0, "failures": 0, "retries": 0, "prompt_tokens": 0, "output_tokens": 0, "seconds": 0.0}


def _check_local(url: str) -> None:
    host = urlparse(url).hostname or ""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise LLMError(f"Refusing to use non-local Ollama host '{host}'. LexLocal only talks to 127.0.0.1.")


class OllamaClient:
    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.model = model or config.MODEL
        self.base_url = (base_url or config.OLLAMA_URL).rstrip("/")
        _check_local(self.base_url)
        self.timeout = timeout or config.LLM_TIMEOUT
        self.session = requests.Session()
        self.session.trust_env = False  # never route through system proxies

    # -- health ---------------------------------------------------------
    def health(self) -> dict:
        try:
            r = self.session.get(f"{self.base_url}/api/tags", timeout=3)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "models": names, "model_available": self.model in names}
        except Exception as e:
            return {"ok": False, "models": [], "model_available": False, "error": type(e).__name__}

    # -- raw call ---------------------------------------------------------
    def _chat(self, messages: list[dict], schema: Optional[dict], max_tokens: int,
              temperature: Optional[float] = None, seed: int = 7) -> tuple[str, dict]:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "think": False,
            "options": {
                "temperature": config.LLM_TEMPERATURE if temperature is None else temperature,
                "num_ctx": config.LLM_NUM_CTX,
                "num_predict": max_tokens,
                "seed": seed,
            },
        }
        if schema is not None:
            body["format"] = schema
        t0 = time.perf_counter()
        try:
            r = self.session.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
            if r.status_code == 400 and "think" in r.text.lower():
                body.pop("think")  # model without thinking support
                r = self.session.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
        except requests.Timeout:
            raise LLMError(f"The local model did not answer within {self.timeout:.0f}s.")
        except requests.ConnectionError:
            raise LLMError("Cannot reach Ollama at 127.0.0.1:11434. Is it running? (`ollama serve`)")
        if r.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {r.status_code}. Is the model '{self.model}' pulled?")
        data = r.json()
        dt = time.perf_counter() - t0
        meta = {
            "seconds": dt,
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0),
            "eval_seconds": data.get("eval_duration", 0) / 1e9,
            "done_reason": data.get("done_reason", ""),
        }
        with _stats_lock:
            STATS["calls"] += 1
            STATS["prompt_tokens"] += meta["prompt_tokens"]
            STATS["output_tokens"] += meta["output_tokens"]
            STATS["seconds"] += dt
        tps = meta["output_tokens"] / meta["eval_seconds"] if meta["eval_seconds"] else 0
        log.info("llm call model=%s in_tok=%d out_tok=%d %.1fs %.1ftok/s",
                 self.model, meta["prompt_tokens"], meta["output_tokens"], dt, tps)
        return data.get("message", {}).get("content", ""), meta

    def generate_text(self, system: str, user: str, max_tokens: int = 300) -> str:
        content, _ = self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}], None, max_tokens)
        return content.strip()

    def generate_json(self, system: str, user: str, model_cls: Type[BaseModel], max_tokens: Optional[int] = None,
                      temperature: Optional[float] = None, seed: int = 7) -> BaseModel:
        """Return a validated instance of model_cls. One retry with a repair hint; else LLMError."""
        schema = model_cls.model_json_schema()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_err = ""
        budget = max_tokens or config.LLM_MAX_TOKENS
        for attempt in range(2):
            content, meta = self._chat(messages, schema, budget, temperature, seed)
            if meta.get("done_reason") == "length":
                # Truncated at num_predict: a repair prompt cannot fix that, a larger budget can.
                last_err = "output truncated"
                with _stats_lock:
                    STATS["retries"] += 1
                log.warning("llm output truncated at %d tokens, attempt %d", budget, attempt + 1)
                budget = int(budget * 1.75)
                continue
            try:
                return model_cls.model_validate(json.loads(_strip_fences(content)))
            except (json.JSONDecodeError, ValidationError) as e:
                last_err = type(e).__name__
                with _stats_lock:
                    STATS["retries"] += 1
                log.warning("llm output failed validation (%s), attempt %d", last_err, attempt + 1)
                messages = messages + [
                    {"role": "assistant", "content": content[:2000]},
                    {"role": "user", "content": "That was not valid JSON for the required schema. Reply again with ONLY valid JSON matching the schema."},
                ]
        with _stats_lock:
            STATS["failures"] += 1
        raise LLMError(f"Model output was not valid JSON after retry ({last_err}).")


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        s = s.rsplit("```", 1)[0]
    return s.strip()
