"""签名边界（工作包 §一 条件③，A 099）—— **这条会红**，所以它是有量具的那条。

lifemint_llm 的公开函数/类，其参数与返回类型必须全部来自标准库或本包。一旦签名里出现实例（darling）的类型，
包就被实例绑架了 —— 而 import 闭包查不出这个（调用方 import 它是合法的）。

规矩 5 内置：最后一段用一个不在白名单的类型造一个假签名，检查器必须报出来；报不出来这条测试自己就是装饰。
"""

from __future__ import annotations

import dataclasses
import inspect
import sys
import typing

import lifemint_llm

ALLOWED_TOP_MODULES = {"builtins", "typing", "collections", "collections.abc", "dataclasses", "lifemint_llm", "types"}


def _module_of(tp: object) -> str | None:
    mod = getattr(tp, "__module__", None)
    return mod if isinstance(mod, str) else None


def _leaf_types(tp: object) -> list[object]:
    """把 Sequence[Message] | None 这类拆到叶子类型。"""
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin is None and not args:
        return [tp]
    out: list[object] = []
    if origin is not None:
        out.extend(_leaf_types(origin))
    for a in args:
        if a is Ellipsis or a is type(None):
            continue
        out.extend(_leaf_types(a))
    return out


def _allowed(tp: object) -> bool:
    if tp is None or tp is type(None) or tp is typing.Any:
        return True
    mod = _module_of(tp)
    if mod is None:
        return True  # 字符串/特殊形式，放过
    top = mod.split(".")[0]
    return top in ALLOWED_TOP_MODULES or mod in ALLOWED_TOP_MODULES or mod in sys.stdlib_module_names or top in sys.stdlib_module_names


def violations_for(obj: object, where: str) -> list[str]:
    bad: list[str] = []
    try:
        hints = typing.get_type_hints(obj)
    except Exception as exc:  # noqa: BLE001 —— 注解解析不了本身就是一条
        return [f"{where}: cannot resolve annotations ({exc})"]
    for name, tp in hints.items():
        for leaf in _leaf_types(tp):
            if not _allowed(leaf):
                bad.append(f"{where}.{name}: {leaf!r} from {_module_of(leaf)}")
    return bad


def public_surface_violations() -> list[str]:
    bad: list[str] = []
    for name in lifemint_llm.__all__:
        obj = getattr(lifemint_llm, name)
        if inspect.isclass(obj):
            if dataclasses.is_dataclass(obj):
                bad += violations_for(obj, name)
            for meth_name, meth in inspect.getmembers(obj, predicate=inspect.isfunction):
                if meth_name.startswith("_") and meth_name != "__init__":
                    continue
                bad += violations_for(meth, f"{name}.{meth_name}")
            for prop_name, prop in inspect.getmembers(obj, lambda m: isinstance(m, property)):
                if prop.fget is not None:
                    bad += violations_for(prop.fget, f"{name}.{prop_name}")
        elif inspect.isfunction(obj):
            bad += violations_for(obj, name)
    return bad


def test_public_signatures_use_only_stdlib_and_this_package() -> None:
    bad = public_surface_violations()
    assert bad == [], "\n".join(bad)


class Alien:  # 模拟实例的类型（模块级：from __future__ import annotations 下 get_type_hints 只认模块全局）
    pass


def _poisoned(x: Alien) -> Alien:  # noqa: ARG001
    return x


def test_the_checker_itself_can_go_red() -> None:
    """规矩 5：一个不在白名单的类型（本测试模块自己的类）出现在签名里，检查器必须报 —— 参数与返回各一条。"""
    bad = violations_for(_poisoned, "poisoned")
    assert len(bad) == 2, bad
    assert all("Alien" in b for b in bad), bad
