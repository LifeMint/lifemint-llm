"""错误分类。重点不是层级，是**失败发生在哪一步**（A 103 §四：重试是幂等性问题）。

    RequestNotSentError      连接建立失败 / DNS / TLS 握手失败 —— 请求**未发出**，可以重试
    ResponseNotReceivedError 已发出、没等到响应（RemoteDisconnected / IncompleteRead / 读超时）—— **不重试**；
                             它可能已被处理（第二次就是第二次真实调用），只标记 maybe_duplicate 让账能对上
    HTTPStatusError          对端回了非 2xx；status 与截断的正文片段（不含 key）
"""


class LLMError(Exception):
    """本包所有错误的根。"""


class ConfigError(LLMError):
    """vendor.json 不合法。"""


class TransportError(LLMError):
    """传输层错误的根。"""

    #: 这次请求有没有可能已被对端处理过（账要按「可能重复」记）。
    maybe_duplicate: bool = False


class RequestNotSentError(TransportError):
    """请求未发出：连接拒绝 / DNS / TLS 握手 / 连接超时。可安全重试。"""

    maybe_duplicate = False


class ResponseNotReceivedError(TransportError):
    """请求已发出但没等到完整响应。**不重试**，标记 maybe_duplicate。"""

    maybe_duplicate = True


class HTTPStatusError(LLMError):
    def __init__(self, status: int, body_snippet: str) -> None:
        super().__init__(f"HTTP {status}: {body_snippet}")
        self.status = status
        self.body_snippet = body_snippet
