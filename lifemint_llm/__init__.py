"""lifemint_llm —— 模型厂商客户端旁挂包（标准库 only）。

方向只有一个：实例与云主机空间 import 本包；`lifemint-core` 永不 import 本包（底座无网）。

公开面（签名边界：参数与返回类型全部来自标准库或本包）：
    Config, load_config, KNOWN_FORMATS
    Message, Completion
    Client
    LLMError, ConfigError, TransportError, HTTPStatusError, RequestNotSentError, ResponseNotReceivedError
"""

from .client import Client
from .config import KNOWN_FORMATS, Config, load_config
from .errors import (
    ConfigError,
    HTTPStatusError,
    LLMError,
    RequestNotSentError,
    ResponseNotReceivedError,
    TransportError,
)
from .types import Completion, Message

__all__ = [
    "Client",
    "Completion",
    "Config",
    "ConfigError",
    "HTTPStatusError",
    "KNOWN_FORMATS",
    "LLMError",
    "Message",
    "RequestNotSentError",
    "ResponseNotReceivedError",
    "TransportError",
    "load_config",
]
