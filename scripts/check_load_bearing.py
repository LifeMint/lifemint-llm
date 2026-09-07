#!/usr/bin/env python3
"""承重测试的执行核对（A 091 §六）：清单里每一条都要有「跑过并通过」的记录。

用法：
    python -m pytest -v tests | python scripts/check_load_bearing.py

读 stdin（pytest -v 的文本），找 "<nodeid> PASSED"。缺 / FAILED / SKIPPED → 红。部分运行让条目"没出现"—— 那正是要它红的。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    wanted = [
        line.strip() for line in (root / "tests" / "LOAD_BEARING_TESTS.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    seen: dict[str, str] = {}
    pat = re.compile(r"^(tests/\S+::\S+)\s+(PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)")
    for raw in sys.stdin:
        m = pat.match(raw.strip().replace("\\", "/"))
        if m:
            seen[m.group(1)] = m.group(2)
    bad = 0
    for w in wanted:
        st = seen.get(w)
        mark = "跑过并通过" if st == "PASSED" else f"**{st or '没跑'}**"
        if st != "PASSED":
            bad += 1
        print(f"  {mark:<10} {w}")
    if bad:
        print(f"\n承重核对：{bad} 条不是「跑过并通过」—— 分不出来的绿按没跑记。")
        return 1
    print(f"\n承重核对：{len(wanted)} 条全部「跑过并通过」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
