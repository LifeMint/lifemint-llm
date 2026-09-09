"""四族接口的请求体与响应解析。**首发只有 openai-chat-compatible 在真机上会被量**；其余三族是按公开文档写的形状，
标 [未在真机量过]，第一次真机调用之前不许当作已验。"""

from __future__ import annotations

from typing import Mapping, Sequence

from .config import Config
from .types import Completion, Message


def build_headers(cfg: Config) -> dict[str, str]:
    if cfg.format == "anthropic-messages":
        return {"x-api-key": cfg.key, "anthropic-version": "2023-06-01"}
    if cfg.format == "gemini-generate-content":
        return {"x-goog-api-key": cfg.key}
    return {"Authorization": f"Bearer {cfg.key}"}


def build_body(cfg: Config, messages: Sequence[Message], *, max_tokens: int, temperature: float, json_object: bool) -> dict[str, object]:
    if cfg.format == "openai-chat-compatible":
        body: dict[str, object] = {
            "model": cfg.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if cfg.effort:
            # 推理努力程度：只在这一族发；网关不认（400/422）由 client 去掉重发一次。
            body["reasoning_effort"] = cfg.effort
        if json_object:
            # A 103 §三①：这家网关要求消息里出现 "json" 字样，否则 400 —— 调用方负责在 prompt 里写；这里只挂字段，400/422 由 Client 回退。
            body["response_format"] = {"type": "json_object"}
        return body
    if cfg.format == "openai-responses":  # [未在真机量过]
        return {
            "model": cfg.model,
            "input": [{"role": m.role, "content": m.content} for m in messages],
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }
    if cfg.format == "anthropic-messages":  # [未在真机量过]
        system = "\n".join(m.content for m in messages if m.role == "system")
        body = {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages if m.role != "system"],
        }
        if system:
            body["system"] = system
        return body
    if cfg.format == "gemini-generate-content":  # [未在真机量过]
        contents = [{"role": "user" if m.role != "assistant" else "model", "parts": [{"text": m.content}]} for m in messages if m.role != "system"]
        body = {"contents": contents, "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}}
        system = "\n".join(m.content for m in messages if m.role == "system")
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body
    raise ValueError(cfg.format)  # pragma: no cover


def _usage(raw: object) -> Mapping[str, int]:
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, int] = {}
    for k, v in raw.items():
        if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
            out[str(k)] = v
    return out


def parse_response(cfg: Config, status_headers: Mapping[str, str], data: Mapping[str, object]) -> Completion:
    rid = status_headers.get("x-request-id") or (data.get("id") if isinstance(data.get("id"), str) else None)
    if cfg.format == "openai-chat-compatible":
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ValueError("chat response has no choices")
        first = choices[0]
        msg = first.get("message") if isinstance(first.get("message"), Mapping) else {}
        text = msg.get("content") if isinstance(msg, Mapping) else None
        return Completion(
            text=text if isinstance(text, str) else "",
            model=str(data.get("model") or cfg.model),
            finish_reason=first.get("finish_reason") if isinstance(first.get("finish_reason"), str) else None,
            usage=_usage(data.get("usage")),
            backend_request_id=rid if isinstance(rid, str) else None,
        )
    if cfg.format == "openai-responses":  # [未在真机量过]
        text = data.get("output_text")
        if not isinstance(text, str):
            parts: list[str] = []
            for item in data.get("output") or []:
                if isinstance(item, Mapping):
                    for c in item.get("content") or []:
                        if isinstance(c, Mapping) and isinstance(c.get("text"), str):
                            parts.append(c["text"])
            text = "".join(parts)
        return Completion(text=text, model=str(data.get("model") or cfg.model), finish_reason=None, usage=_usage(data.get("usage")),
                          backend_request_id=rid if isinstance(rid, str) else None)
    if cfg.format == "anthropic-messages":  # [未在真机量过]
        parts = [c["text"] for c in (data.get("content") or []) if isinstance(c, Mapping) and isinstance(c.get("text"), str)]
        return Completion(text="".join(parts), model=str(data.get("model") or cfg.model),
                          finish_reason=data.get("stop_reason") if isinstance(data.get("stop_reason"), str) else None,
                          usage=_usage(data.get("usage")), backend_request_id=rid if isinstance(rid, str) else None)
    if cfg.format == "gemini-generate-content":  # [未在真机量过]
        cands = data.get("candidates") or []
        text = ""
        finish = None
        if cands and isinstance(cands[0], Mapping):
            content = cands[0].get("content") if isinstance(cands[0].get("content"), Mapping) else {}
            text = "".join(p["text"] for p in (content.get("parts") or []) if isinstance(p, Mapping) and isinstance(p.get("text"), str))
            fr = cands[0].get("finishReason")
            finish = fr if isinstance(fr, str) else None
        return Completion(text=text, model=cfg.model, finish_reason=finish, usage=_usage(data.get("usageMetadata")),
                          backend_request_id=rid if isinstance(rid, str) else None)
    raise ValueError(cfg.format)  # pragma: no cover
