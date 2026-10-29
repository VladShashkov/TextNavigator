"""CLI: python -m textnavigator documents/ --date 2026-03-10 [--json]"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .pipeline import analyze

MARK = {"ok": "", "no_data": "", "needs_review": " ⚠ требует проверки"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Проверка условий договоров поставки")
    ap.add_argument("paths", nargs="+", help="TXT-файлы или папки")
    ap.add_argument("--date", default="2026-03-10", help="дата проверки, ГГГГ-ММ-ДД")
    ap.add_argument("--json", action="store_true", help="вывести полный JSON")
    a = ap.parse_args(argv)

    files = []
    for p in map(Path, a.paths):
        for f in sorted(p.glob("*.txt")) if p.is_dir() else [p]:
            files.append((f.name, f.read_bytes()))
    res = analyze(files, date.fromisoformat(a.date))
    if a.json:
        json.dump(res, sys.stdout, ensure_ascii=False, indent=2)
        return 0

    print(f"Дата проверки: {date.fromisoformat(a.date):%d.%m.%Y}\n")
    for c in res["contracts"]:
        print(f"■ {c['number']} — {c['supplier']['display']}")
        for key, name in (("amount", "Сумма"), ("deadline", "Срок поставки")):
            f = c[key]
            src = f"  [{f['evidence']['file']}, {f['evidence']['para_label']}]" if f["evidence"] else ""
            ch = f"  (изменено: {f['changed_by']})" if f["changed_by"] else ""
            print(f"  {name}: {f['display']}{MARK[f['status']]}{ch}{src}")
            for n in f["notes"]:
                print(f"      · {n}")
            for pr in f["proposals"]:
                print(f"      ↳ не согласовано: {pr['display']} — {pr['doc_title']} ({pr['doc']}): {pr['reason']}")
        for i in c["issues"]:
            print(f"  ⚠ {i}")
        print()
    for u in res["unassigned"]:
        print(f"? {u['file']}: {'; '.join(u['problems'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
