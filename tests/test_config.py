"""vendor.json → Config；最终 POST 地址与 lifemint-vps 的表逐字相等；describe 永不含 key。"""

from __future__ import annotations

import json
import os
import sys

import pytest

from lifemint_llm import Config, ConfigError, load_config

# 与 lifemint-vps internal/vendors.EndpointURL 同一张表（两处必须逐字相等）。
VPS_TABLE = {
    "openai-chat-compatible": "https://api.sensoft.top/v1/chat/completions",
    "openai-responses": "https://api.openai.com/v1/responses",
    "anthropic-messages": "https://api.anthropic.com/v1/messages",
    "gemini-generate-content": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent",
}
BASES = {
    "openai-chat-compatible": "https://api.sensoft.top/v1",
    "openai-responses": "https://api.openai.com/v1",
    "anthropic-messages": "https://api.anthropic.com",
    "gemini-generate-content": "https://generativelanguage.googleapis.com",
}


def test_endpoint_urls_match_the_vps_table() -> None:
    for fmt, want in VPS_TABLE.items():
        cfg = Config(vendor="x", format=fmt, base_url=BASES[fmt], key="k", model="gemini-2.5-pro" if "gemini" in fmt else "m")
        assert cfg.endpoint_url() == want, fmt


def test_load_config_reads_vendor_json_and_never_prints_the_key(tmp_path) -> None:
    p = tmp_path / "vendor.json"
    p.write_text(json.dumps({"vendor": "openai", "format": "openai-chat-compatible", "base_url": "https://api.sensoft.top/v1",
                             "key": "sk-SECRET-123", "model": "gpt-5.6-luna"}), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(p, 0o600)
    cfg = load_config(str(p), proxy_url="http://127.0.0.1:3128")
    assert cfg.model == "gpt-5.6-luna" and cfg.proxy_url == "http://127.0.0.1:3128"
    line = cfg.describe()
    assert "sk-SECRET" not in line
    assert line == "openai POST https://api.sensoft.top/v1/chat/completions format=openai-chat-compatible model=gpt-5.6-luna proxy=http://127.0.0.1:3128"
    if sys.platform != "win32":
        os.chmod(p, 0o644)
        with pytest.raises(ConfigError):
            load_config(str(p))


def test_bad_configs_are_rejected() -> None:
    with pytest.raises(ConfigError):
        Config(vendor="x", format="grpc", base_url="https://a/v1", key="k")
    with pytest.raises(ConfigError):
        Config(vendor="x", format="openai-chat-compatible", base_url="http://a/v1", key="k")
    with pytest.raises(ConfigError):
        Config(vendor="x", format="openai-chat-compatible", base_url="https://a/v1", key="  ")
    with pytest.raises(ConfigError):
        Config(vendor="x", format="openai-chat-compatible", base_url="https://a/v1", key="k", proxy_url="socks5://x")
