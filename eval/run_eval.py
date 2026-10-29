"""Оценка на эталонном наборе: python eval/run_eval.py

Метрики:
  - точность по полю: значение и статус совпали с эталоном;
  - верное основание: у найденного значения правильный файл-источник;
  - выдуманные значения: эталон «нет данных», а система вернула число/дату (должно быть 0);
  - несогласованные изменения: найдены все предложения из эталона;
  - валидность цитат: доля цитат, совпавших с исходным текстом дословно.
"""
from __future__ import annotations

import glob
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from textnavigator.pipeline import analyze  # noqa: E402


def load(patterns):
    files = []
    for pat in patterns:
        for f in sorted(glob.glob(str(ROOT / pat))):
            files.append((Path(f).name, Path(f).read_bytes()))
    return files


def main() -> int:
    cases = json.loads((ROOT / "eval/cases.json").read_text(encoding="utf-8"))["cases"]
    n = ok = src_n = src_ok = fabricated = prop_n = prop_ok = 0
    quotes = quotes_ok = 0
    fails = []
    for case in cases:
        res = analyze(load(case["files"]), date.fromisoformat(case["check_date"]))
        texts = {d["filename"]: d["text"] for d in res["documents"]}
        by_no = {c["number"]: c for c in res["contracts"]}
        for c in res["contracts"]:
            for k in ("amount", "deadline"):
                evs = [c[k]["evidence"]] + [p["evidence"] for p in c[k]["proposals"]]
                for ev in filter(None, evs):
                    quotes += 1
                    quotes_ok += texts[ev["file"]][ev["start"]:ev["end"]] == ev["quote"]
        for number, exp in case["expected"].items():
            got = by_no.get(number)
            for k in ("amount", "deadline"):
                if k not in exp:
                    continue
                value, status, src = exp[k]
                n += 1
                f = got[k] if got else None
                gv = f["value"] if f else None
                match = f is not None and gv == value and f["status"] == status
                ok += match
                if not match:
                    fails.append(f"{case['name']} · {number}.{k}: ждали {value}/{status}, "
                                 f"получили {gv}/{f['status'] if f else '—'}")
                if value is None and gv is not None:
                    fabricated += 1
                if f and f["evidence"]:
                    src_n += 1
                    src_ok += f["evidence"]["file"] == src
            if "deadline_proposals" in exp:
                prop_n += 1
                got_p = sorted(p["display"] for p in got["deadline"]["proposals"]) if got else []
                hit = got_p == sorted(exp["deadline_proposals"])
                prop_ok += hit
                if not hit:
                    fails.append(f"{case['name']} · {number}: предложения {got_p} ≠ {exp['deadline_proposals']}")

    pct = lambda a, b: f"{a}/{b} ({100 * a / b:.0f}%)" if b else "—"
    print(f"Кейсов: {len(cases)}, проверяемых полей: {n}")
    print(f"Точность по полю (значение + статус): {pct(ok, n)}")
    print(f"Верный файл-основание:                {pct(src_ok, src_n)}")
    print(f"Несогласованные изменения найдены:    {pct(prop_ok, prop_n)}")
    print(f"Выдуманные значения:                  {fabricated}")
    print(f"Цитаты дословно совпадают с текстом:  {pct(quotes_ok, quotes)}")
    for f in fails:
        print("  ✗", f)
    return 1 if fails or fabricated else 0


if __name__ == "__main__":
    raise SystemExit(main())
