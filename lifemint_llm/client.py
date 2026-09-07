"""Client.complete()：一次补全 = 一到两次 HTTP 调用，账按 HTTP 调用数记。

三条与网关打架的约束一起设计（A 103 §三/§四）：
- **≥ min_interval_s 间隔**：两次 HTTP 请求之间至少隔这么久（含重试、含回退），不是两次 complete 之间。
- **重试只对「未发出」**（RequestNotSentError），最多一次，且重试前也要过间隔闸；「已发出没等到响应」不重试，原样抛出（maybe_duplicate=True）。
- **json_object 回退**：400/422 且带 response_format → 去掉它重发一次；这一次也是一次真实调用，http_calls=2。
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Sequence

from .config import Config
from .errors import HTTPStatusError, RequestNotSentError
from .formats import build_body, build_headers, parse_response
from .transport import Transport
from .types import Completion, Message

_log = logging.getLogger("lifemint_llm")


class Client:
    def __init__(
        self,
        config: Config,
        *,
        min_interval_s: float = 2.0,
        connect_retries: int = 1,
        timeout_s: float = 60.0,
        transport: Transport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._cfg = config
        self._min_interval = min_interval_s
        self._connect_retries = connect_retries
        self._transport = transport or Transport(config.proxy_url, timeout_s=timeout_s)
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None

    @property
    def config(self) -> Config:
        return self._cfg

    def self_check(self) -> str:
        """启动自检：把拼好的完整地址印一行（不含 key）。与 lifemint-vps 启动日志那一行逐字相等才算对（A 103 §一，C 的判别法）。"""
        line = self._cfg.describe()
        _log.info("lifemint_llm self-check: %s", line)
        return line

    def _pace(self) -> None:
        if self._last_call is not None:
            wait = self._min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def _post(self, body: dict[str, object]) -> tuple[int, dict[str, object], dict[str, str]]:
        """一次 HTTP 调用，带间隔闸；「未发出」最多再试 connect_retries 次。"""
        url = self._cfg.endpoint_url()
        headers = build_headers(self._cfg)
        attempts = 0
        while True:
            self._pace()
            attempts += 1
            try:
                status, data, resp_headers = self._transport.post_json(url, headers, body)
                return status, data, dict(resp_headers)
            except RequestNotSentError as exc:
                if attempts > self._connect_retries:
                    raise
                _log.warning("lifemint_llm: request not sent (%s); retrying once", exc)

    def complete(
        self,
        messages: Sequence[Message],
        *,
        max_tokens: int = 768,
        temperature: float = 0.7,
        json_object: bool = False,
    ) -> Completion:
        if not messages:
            raise ValueError("messages must not be empty")
        body = build_body(self._cfg, messages, max_tokens=max_tokens, temperature=temperature, json_object=json_object)
        calls = 1
        try:
            status, data, headers = self._post(body)
        except HTTPStatusError as exc:
            if json_object and exc.status in (400, 422) and self._cfg.format == "openai-chat-compatible":
                # A 103 §三①：网关对 json_object 挑剔 → 去掉 response_format 重发一次。这是第二次真实调用，账记 2。
                _log.warning("lifemint_llm: %s with response_format; retrying once without it", exc)
                body.pop("response_format", None)
                calls = 2
                status, data, headers = self._post(body)
            else:
                raise
        completion = parse_response(self._cfg, headers, data)
        if calls != 1:
            completion = Completion(
                text=completion.text, model=completion.model, finish_reason=completion.finish_reason,
                usage=completion.usage, backend_request_id=completion.backend_request_id, http_calls=calls,
            )
        _log.info("lifemint_llm: completion ok status=%s http_calls=%d request_id=%s", status, calls, completion.backend_request_id)
        return completion
