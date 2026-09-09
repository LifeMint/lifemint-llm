"""假网关上的四条真实路径（openai-chat-compatible；A 103 §三/§四）：

① 成功：Bearer 进头、body 形状对、解析 choices/usage、http_calls=1。
② json_object 撞 400 → 去掉 response_format 重发一次 → 成功，http_calls=2，网关看到两次请求。
③ 网关收到请求后不回就断（RemoteDisconnected）→ ResponseNotReceivedError（maybe_duplicate=True），**只发了一次**，不重试。
④ 连接拒绝（端口没人听）→ 重试一次后 RequestNotSentError；两次尝试之间过了 ≥2s 的间隔闸（假时钟量）。
⑤ 环境变量里的代理**被忽略**：HTTPS_PROXY 指向一个没人听的端口，请求照样直达假网关（Zero Telemetry §七.5 那次喂绿的病）。
⑥ 两次 complete 背靠背：第二次前 sleep ≥ 2s（间隔闸作用在 HTTP 调用上）。
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import threading

import pytest

from lifemint_llm import Client, Config, Message, RequestNotSentError, ResponseNotReceivedError

# 假网关只听 http；Config 要求 https，所以测试里用一个允许 http 的 Config 子类绕过 —— 这不是产线路径，产线永远 https。


class _HTTPOKConfig(Config):
    def __post_init__(self) -> None:  # 放过 http 只为本地假网关
        pass


class Gateway(http.server.BaseHTTPRequestHandler):
    mode = "ok"
    seen: list[dict] = []

    def log_message(self, *_: object) -> None:  # 静音
        pass

    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n) or b"{}")
        Gateway.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if Gateway.mode == "disconnect":
            self.connection.close()  # 收到了，不回
            return
        if Gateway.mode == "reject_effort" and "reasoning_effort" in body:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"Unrecognized request argument: reasoning_effort"}}')
            return
        if Gateway.mode == "reject_json_object" and "response_format" in body:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"response_format needs the word json in messages"}}')
            return
        out = {"id": "chatcmpl-1", "model": body.get("model"), "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}}
        raw = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def gateway():
    Gateway.seen = []
    Gateway.mode = "ok"
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def _client(srv, **kw) -> tuple[Client, FakeClock]:
    port = srv.server_address[1]
    cfg = _HTTPOKConfig(vendor="openai", format="openai-chat-compatible", base_url=f"http://127.0.0.1:{port}/v1", key="sk-test", model="m1")
    clk = FakeClock()
    return Client(cfg, clock=clk.now, sleep=clk.sleep, timeout_s=5, **kw), clk


MSGS = [Message("system", "answer in json"), Message("user", "hello")]


def test_success_path(gateway) -> None:
    c, _ = _client(gateway)
    out = c.complete(MSGS, max_tokens=32, temperature=0.1)
    assert out.text == "hi" and out.finish_reason == "stop" and out.usage["total_tokens"] == 4 and out.http_calls == 1
    assert out.backend_request_id == "chatcmpl-1"
    req = Gateway.seen[0]
    assert req["path"] == "/v1/chat/completions" and req["auth"] == "Bearer sk-test"
    assert req["body"]["messages"][1] == {"role": "user", "content": "hello"} and req["body"]["max_tokens"] == 32
    assert c.self_check().startswith("openai POST http://127.0.0.1:")


def test_json_object_falls_back_once_and_counts_two_calls(gateway) -> None:
    Gateway.mode = "reject_json_object"
    c, _ = _client(gateway)
    out = c.complete(MSGS, json_object=True)
    assert out.text == "hi" and out.http_calls == 2
    assert len(Gateway.seen) == 2
    assert "response_format" in Gateway.seen[0]["body"] and "response_format" not in Gateway.seen[1]["body"]


def test_remote_disconnect_is_not_retried_and_is_flagged_maybe_duplicate(gateway) -> None:
    Gateway.mode = "disconnect"
    c, _ = _client(gateway)
    with pytest.raises(ResponseNotReceivedError) as ei:
        c.complete(MSGS)
    assert ei.value.maybe_duplicate is True
    assert len(Gateway.seen) == 1  # 只发了一次：已发出没等到响应的不重试


def test_connection_refused_is_retried_once_with_pacing() -> None:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # 现在这个端口没人听
    cfg = _HTTPOKConfig(vendor="openai", format="openai-chat-compatible", base_url=f"http://127.0.0.1:{port}/v1", key="k", model="m")
    clk = FakeClock()
    c = Client(cfg, clock=clk.now, sleep=clk.sleep, timeout_s=2)
    with pytest.raises(RequestNotSentError) as ei:
        c.complete(MSGS)
    assert ei.value.maybe_duplicate is False
    assert clk.sleeps and all(s >= 1.99 for s in clk.sleeps), clk.sleeps  # 重试前过了间隔闸


def test_environment_proxy_is_ignored(gateway, monkeypatch) -> None:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    dead = s.getsockname()[1]
    s.close()
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        monkeypatch.setenv(var, f"http://127.0.0.1:{dead}")
    # 这台开发机上 Clash 设了 NO_PROXY=localhost,127.0.0.1,…：不清掉它，urllib 对回环目标一律绕过代理，这条守卫就**恒绿**
    # （2026-09-07 规矩 5 打红时发现：把 ProxyHandler(proxies) 改成 ProxyHandler() 测试照样过）。清掉之后才是真守卫。
    for var in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(var, raising=False)
    import urllib.request
    assert urllib.request.getproxies().get("http", "").endswith(str(dead)), "前提：环境里确实有代理，否则本测试量不到东西"
    assert not urllib.request.proxy_bypass("127.0.0.1"), "前提：回环没被 NO_PROXY 绕过，否则本测试恒绿"
    c, _ = _client(gateway)
    out = c.complete(MSGS)
    assert out.text == "hi" and len(Gateway.seen) == 1  # 没走环境变量里的代理


def test_two_completions_are_paced(gateway) -> None:
    c, clk = _client(gateway, min_interval_s=2.0)
    c.complete(MSGS)
    c.complete(MSGS)
    assert clk.sleeps and clk.sleeps[0] >= 1.99, clk.sleeps


def test_effort_is_sent_as_reasoning_effort_and_dropped_once_when_the_gateway_rejects_it(gateway) -> None:
    """Sponsor 2026-09-09：effort 字段。设了就发 reasoning_effort；网关 400 就去掉重发一次（http_calls=2），与 json_object 同一条回退。"""
    c, clk = _client(gateway)
    port = gateway.server_address[1]
    cfg2 = _HTTPOKConfig(vendor="openai", format="openai-chat-compatible", base_url=f"http://127.0.0.1:{port}/v1", key="sk-test", model="m1", effort="high")
    c_effort = Client(cfg2, clock=clk.now, sleep=clk.sleep, timeout_s=5)
    Gateway.mode = "ok"
    Gateway.seen.clear()
    out = c_effort.complete(MSGS, max_tokens=8)
    assert out.http_calls == 1 and Gateway.seen[0]["body"]["reasoning_effort"] == "high"
    Gateway.mode = "reject_effort"
    Gateway.seen.clear()
    out = c_effort.complete(MSGS, max_tokens=8)
    assert out.text == "hi" and out.http_calls == 2 and len(Gateway.seen) == 2
    assert "reasoning_effort" in Gateway.seen[0]["body"] and "reasoning_effort" not in Gateway.seen[1]["body"]
    # 没设 effort：请求体里根本没有这个字段
    Gateway.mode = "ok"
    Gateway.seen.clear()
    c.complete(MSGS, max_tokens=8)
    assert "reasoning_effort" not in Gateway.seen[0]["body"]
