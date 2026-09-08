# lifemint-llm

A small, optional, network-touching client package: it knows how to send a
request to a hosted model vendor and bring the answer back. Nothing else.

## Direction (read this first)

```
lifemint-core   does NOT import lifemint-llm.
                The reference runtime is dependency-free and does not touch the
                network; that stays true.
instances       (a personal instance, the neutral default instance, a hosted
                space) DO import lifemint-llm, if and when they want to talk to
                a hosted vendor instead of a local model.
```

This arrow only points one way. A change that makes `lifemint-core` depend on
this package is a change to the base's core promise, not a refactor.

## Why it is a separate repository

It could not live in either of the two places that already exist:

- **Not in the base** (`lifemint-core`): the base declares "no network or
  automatic delivery" in its first paragraph. A vendor HTTP client makes that
  sentence false.
- **Not in an instance**: then every other instance either imports someone
  else's private instance, or reimplements it.

So it is a third thing: optional, network-touching, importable by anyone.

## Scope

**In scope**

- Speaking the wire formats of hosted vendors (OpenAI-compatible chat
  completions first; others as they are actually tested).
- Reading a vendor descriptor (format / base URL / model) that the caller
  hands it.

**Out of scope — deliberately**

- Deciding *what* to say. That is the caller's business.
- Holding or discovering credentials. Keys are passed in by the caller, which
  reads them from wherever it keeps secrets. This package never reads a key
  file, never logs a key, and never puts a key on a command line.
- Anything that knows about a particular instance. If a public signature in
  this package ever takes or returns a type owned by an instance, the package
  has been captured by that instance — that is the boundary to watch, and it
  is the one an import check cannot see.

## Compatibility is measured, not inherited

"OpenAI-compatible" is a claim about an endpoint, not a guarantee. Gateways
that speak one route may not speak another; a base URL that is a valid HTTPS
URL can still be the wrong address. The intended discipline here is to record,
per endpoint, what has actually been exercised — and to treat everything else
as unknown rather than as working.

## Status

Early. The API is not stable and there is no usage example in this README on
purpose: the surface has not settled, and a documented example that drifts from
the code is worse than no example. Read the source.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

---

## 结构与纪律（中文，B 线工作包 V0.1）

**`lifemint-core` 不 import `lifemint_llm`。** 底座保持无网（lifemint-core README：dependency-free, no network）；是实例（darling）与云主机空间（`darling-space@<id>` 的 Core）import 本包。方向只有这一个，不许反过来。

本包是「可选、碰网、谁都能 import」的第三个东西（A 099 裁甲，2026-09-07）：读一份 `vendor.json`（由 lifemint-vps 渲染），按其中的 `format` 调模型厂商。**只用标准库**：`urllib` + `json`，零第三方依赖。

```
lifemint_llm/config.py      vendor.json → Config；format 名单；最终 POST 的完整地址（与 lifemint-vps 启动日志印的那一行必须逐字相等）
lifemint_llm/transport.py   urllib；代理**只走显式 proxy_url，不读环境变量**；把失败分成「请求未发出」与「已发出没等到响应」两类
lifemint_llm/formats.py     openai-chat-compatible（首发、中转类网关默认）/ openai-responses / anthropic-messages / gemini-generate-content 的请求与解析
lifemint_llm/client.py      Client.complete()；≥2s 间隔；重试只对「未发出」；json_object 400/422 去掉 response_format 重发一次并标记
tests/                      签名边界（会红）· import 闭包（恒绿，标注）· 假服务器上的四条真实路径
```

## 三条纪律（工作包 §一，darling 仓 `docs/L1_LIFEMINT_LLM_WORK_PACKAGE_V0.1_2026-09-07.md`）

1. 公开仓；底座不 import 本包。
2. import 闭包守卫（本包不 import darling 私有模块）**是恒绿的**：它说的是「结构上不可能」，不是「测过了没有」，不进承重。
3. **签名边界**才是会红的那条：公开函数/类的参数与返回类型必须全部来自标准库或本包。签名里出现实例的类型 = 包被实例绑架。

## 中转网关的四条（A 103，C 线在同一家网关实测栽过）

- `format` 不按厂商名整包继承：地址非官方 → `openai-chat-compatible`；`openai-responses` 只给显式确认的端点。
- 启动自检印**拼好的完整 URL**（不含 key）：错的往往是拼接结果不是任何一个输入（少 `/v1` 是合法 https 也是错地址）。
- `response_format: json_object` 要求消息里出现 "json" 字样否则 400；400/422 → 去掉 response_format 重发一次。
- 连续请求 ≥2 s；偶发 RemoteDisconnected **不重试**（可能是第二次真实调用，账对不上），只标记 `maybe_duplicate`；重试只对连接建立失败 / DNS / TLS 握手失败。

## 验收（等真机；真机之前只有单测绿，且要标「单测」）

真机：云空间 Core 经 darling-egress 调到网关一次成功；同一进程 strace 全程计数除 127.0.0.1 外零连接；白名单外域名 CONNECT 被拒（拒的是连接不是日志）。
