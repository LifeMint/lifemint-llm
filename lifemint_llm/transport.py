"""urllib 传输。两条硬纪律：

1. **代理只走显式 proxy_url，不读环境变量。** 家庭主机那次（Zero Telemetry §七.5）：urllib 默认读 HTTP_PROXY 走 127.0.0.1:7897 出去，把出站围栏喂绿。
   这里无论有没有 proxy_url，都装一个 ProxyHandler：有就只用它，没有就 `ProxyHandler({})` = 明确不用任何代理。
2. **失败分两类**（A 103 §四）：请求未发出（可重试）与已发出没等到响应（不重试、标 maybe_duplicate）。分类做在这一层，上层不猜。
"""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import urllib.error
import urllib.request
from typing import Mapping

from .errors import HTTPStatusError, RequestNotSentError, ResponseNotReceivedError

_BODY_SNIPPET = 300


class Transport:
    def __init__(self, proxy_url: str | None, *, timeout_s: float = 60.0) -> None:
        proxies: dict[str, str] = {}
        if proxy_url:
            proxies = {"http": proxy_url, "https": proxy_url}
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
        self._timeout = timeout_s

    def post_json(self, url: str, headers: Mapping[str, str], body: Mapping[str, object]) -> tuple[int, dict[str, object], Mapping[str, str]]:
        """POST JSON，返回 (status, 解出的 JSON 对象, 响应头)。非 2xx → HTTPStatusError（正文截断、不含 key）。"""
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        req.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                raw = resp.read()
                status = resp.status
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as exc:
            # 对端回了状态码：请求肯定发出去了，但这不是传输错，是应用层拒。
            snippet = exc.read(_BODY_SNIPPET).decode("utf-8", "replace") if exc.fp else ""
            raise HTTPStatusError(exc.code, snippet.strip()) from None
        except urllib.error.URLError as exc:
            # URLError 包着底层原因：连接拒绝 / DNS / TLS 握手 / 连接超时 → 未发出
            reason = exc.reason
            if isinstance(reason, (http.client.RemoteDisconnected, http.client.IncompleteRead)):
                raise ResponseNotReceivedError(f"response not received: {reason}") from None
            raise RequestNotSentError(f"request not sent: {reason}") from None
        except (http.client.RemoteDisconnected, http.client.IncompleteRead) as exc:
            raise ResponseNotReceivedError(f"response not received: {exc}") from None
        except (socket.timeout, TimeoutError) as exc:
            # 读超时：请求已发出（连接层的超时在 URLError 里）。
            raise ResponseNotReceivedError(f"timed out waiting for response: {exc}") from None
        except (ConnectionRefusedError, ConnectionResetError, ssl.SSLError, OSError) as exc:
            raise RequestNotSentError(f"request not sent: {exc}") from None
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError as exc:
            raise HTTPStatusError(status, f"non-JSON body: {exc}") from None
        if not isinstance(parsed, dict):
            raise HTTPStatusError(status, "JSON body is not an object")
        return status, parsed, resp_headers
