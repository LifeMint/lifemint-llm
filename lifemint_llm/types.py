"""公开的数据形状。与 darling_core.local_llm 的 ChatMessage / CompletionResult **同形但不同类**：
本包不 import 实例，实例要用就自己转一层（工作包 §一 条件③：签名里不能出现实例的类型）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

ROLES = frozenset({"system", "user", "assistant"})


@dataclass(frozen=True)
class Message:
    role: str
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError("message role is unsupported")
        if not isinstance(self.content, str):
            raise ValueError("message content must be a string")


@dataclass(frozen=True)
class Completion:
    text: str = field(repr=False)
    model: str
    finish_reason: str | None
    usage: Mapping[str, int]
    #: 厂商侧的请求 id（若有）；对账用。
    backend_request_id: str | None = None
    #: 这次调用实际发出的 HTTP 请求数（1；json_object 回退时 2）。账要记它，不记「一次 complete」。
    http_calls: int = 1
    #: 有一次「已发出没等到响应」被吞掉后才成功 —— 不会发生（本包不对那类重试），保留字段是为了让读者知道它被考虑过。
    maybe_duplicate: bool = False
