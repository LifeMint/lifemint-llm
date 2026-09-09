"""vendor.json → Config。文件由 lifemint-vps 渲染（secrets/<space>/vendor.json，0600）：

    {"vendor": "openai", "format": "openai-chat-compatible", "base_url": "https://…/v1", "key": "…", "model": "…"}

`format` **照文件做，不按 vendor 名再推一次**（A 103 §二①）。`endpoint_url()` 是最终 POST 的完整地址 ——
启动自检把它印一行（不含 key），必须与 lifemint-vps 启动日志里 `platform=[… POST <url> …]` 那一行逐字相等。"""

from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

from .errors import ConfigError

KNOWN_EFFORTS: tuple[str, ...] = ("", "low", "medium", "high")

KNOWN_FORMATS: tuple[str, ...] = (
    "openai-chat-compatible",
    "openai-responses",
    "anthropic-messages",
    "gemini-generate-content",
)


@dataclass(frozen=True)
class Config:
    vendor: str
    format: str
    base_url: str
    key: str
    model: str = ""
    #: 推理努力程度（Sponsor 2026-09-09：两级 key 文件里的 effort 字段）。"" = 不发，网关按默认；low / medium / high 发成
    #: chat-completions 的 reasoning_effort。只在 openai-chat-compatible 上发；网关 400/422 就去掉重发一次（与 json_object 同一条回退）。
    effort: str = ""
    #: 显式代理地址（http://127.0.0.1:port），**不读环境变量**：云主机上指向 darling-egress。None = 直连、且忽略系统代理。
    proxy_url: str | None = None

    def __post_init__(self) -> None:
        if self.format not in KNOWN_FORMATS:
            raise ConfigError(f"unknown format {self.format!r} (known: {', '.join(KNOWN_FORMATS)})")
        u = urlsplit(self.base_url)
        if u.scheme != "https" or not u.netloc:
            raise ConfigError("base_url must be an https URL")
        if not self.key.strip():
            raise ConfigError("key is required")
        if self.effort not in KNOWN_EFFORTS:
            raise ConfigError(f"unknown effort {self.effort!r} (known: {', '.join(e or '<empty>' for e in KNOWN_EFFORTS)})")
        if self.proxy_url is not None:
            p = urlsplit(self.proxy_url)
            if p.scheme not in ("http", "https") or not p.netloc:
                raise ConfigError("proxy_url must be an http(s) URL")

    def endpoint_url(self) -> str:
        """最终 POST 的完整地址。与 lifemint-vps internal/vendors.EndpointURL 同一张表 —— 两处要逐字相等。"""
        base = self.base_url.rstrip("/")
        if self.format == "openai-chat-compatible":
            return base + "/chat/completions"
        if self.format == "openai-responses":
            return base + "/responses"
        if self.format == "anthropic-messages":
            return base + "/v1/messages"
        if self.format == "gemini-generate-content":
            model = self.model or "{model}"
            return f"{base}/v1beta/models/{model}:generateContent"
        raise ConfigError(f"unknown format {self.format!r}")  # pragma: no cover —— __post_init__ 已拦

    def describe(self) -> str:
        """给启动日志的一行，**永不含 key**。"""
        s = f"{self.vendor} POST {self.endpoint_url()} format={self.format}"
        if self.model:
            s += f" model={self.model}"
        if self.effort:
            s += f" effort={self.effort}"
        if self.proxy_url:
            s += f" proxy={self.proxy_url}"
        return s


def load_config(path: str, *, proxy_url: str | None = None) -> Config:
    """读 vendor.json。非 Windows 上权限比 0600 宽就拒（里面有 key）。"""
    if sys.platform != "win32":
        mode = stat.S_IMODE(os.stat(path).st_mode)
        if mode & 0o077:
            raise ConfigError(f"{path} mode is {mode:#o}, wider than 0600")
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: not a JSON object")
    try:
        return Config(
            vendor=str(raw["vendor"]),
            format=str(raw["format"]),
            base_url=str(raw["base_url"]),
            key=str(raw["key"]),
            model=str(raw.get("model", "") or ""),
            effort=str(raw.get("effort", "") or ""),
            proxy_url=proxy_url,
        )
    except KeyError as exc:
        raise ConfigError(f"{path}: missing {exc.args[0]}") from None
