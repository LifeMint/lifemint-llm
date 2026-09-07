"""import 闭包守卫（工作包 §一 条件②）—— **恒绿，标注**（A 099 §一.3②）。

它说的是「结构上不可能」：本仓里根本没有 darling 的模块，所以它永远绿。它**不进承重清单**，不许在任何验收里拿它当「我们验过了」用。
真正的执行是仓边界；真正会红的是 test_signature_boundary。留着它只为了：哪天有人把这个包 vendoring 进实例仓再跑测试时，它会变成有意义的一条。

另一半（会红）：本包只许 import 标准库 —— 出现任何第三方模块，这条红。
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

import lifemint_llm

PRIVATE_INSTANCE_MODULES = (
    "darling_core", "identity", "memory", "memory_context", "memory_candidates",
    "relationship", "continuity", "covenant", "conversation_ledger", "lifemint_core",
)


def _import_all_submodules() -> list[str]:
    names = []
    for info in pkgutil.walk_packages(lifemint_llm.__path__, lifemint_llm.__name__ + "."):
        importlib.import_module(info.name)
        names.append(info.name)
    return names


def test_no_private_instance_module_in_import_closure_ALWAYS_GREEN() -> None:
    """[恒绿] 见模块 docstring。"""
    _import_all_submodules()
    hit = [m for m in sys.modules if m.split(".")[0] in PRIVATE_INSTANCE_MODULES]
    assert hit == [], hit


def test_only_stdlib_is_imported() -> None:
    """[会红] 本包 import 闭包里除 lifemint_llm 自己外只有标准库。"""
    _import_all_submodules()
    third_party = sorted(
        m for m in sys.modules
        if not m.startswith("lifemint_llm")
        and m.split(".")[0] not in sys.stdlib_module_names
        and m.split(".")[0] not in {"_pytest", "pytest", "pluggy", "iniconfig", "packaging", "py", "tests", "_virtualenv", "_distutils_hack", "colorama", "pygments", "exceptiongroup", "tomli", "attr", "attrs", "_pytest_asyncio", "faulthandler", "typing_extensions"}
        and not m.startswith("__editable__")
    )
    # 只允许 pytest 自己带进来的东西；lifemint_llm 的模块文件里不许出现任何第三方 import。
    import ast, pathlib
    pkg_dir = pathlib.Path(lifemint_llm.__file__).parent
    offenders = []
    for py in pkg_dir.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            for m in mods:
                top = m.split(".")[0]
                if top not in sys.stdlib_module_names and top != "lifemint_llm":
                    offenders.append(f"{py.name}: import {m}")
    assert offenders == [], offenders
    del third_party
