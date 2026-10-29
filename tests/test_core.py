"""Проверки корректности, «нет данных» и учёта статуса документа.

Исходные 6 файлов задания + синтетические ловушки, построенные из них
заменой текста (как на встрече: «изменим одно поле, загрузим новый договор»).
"""
from datetime import date
from pathlib import Path

import pytest

from textnavigator.pipeline import analyze

DOCS = Path(__file__).resolve().parent.parent / "documents"
CHECK = date(2026, 3, 10)


def base_files() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(DOCS.glob("*.txt"))}


def run(files: dict[str, str], check: date = CHECK) -> dict:
    res = analyze(list(files.items()), check)
    assert res["validation_errors"] == []
    return res


def contract(res, number):
    return next(c for c in res["contracts"] if c["number"] == number)


# --- четыре вопроса пользователя ---------------------------------------------

def test_q1_stn101_deadline_changed_by_signed_amendment():
    c = contract(run(base_files()), "STN-101")
    d = c["deadline"]
    assert d["status"] == "ok" and d["value"] == "2026-04-30"
    assert d["evidence"]["file"] == "02_amendment_signed.txt"
    assert "30.04.2026" in d["evidence"]["quote"]
    assert d["changed_by"].startswith("Доп. соглашение № 1")
    assert d["base"]["value"] == "2026-04-15"            # было по договору
    assert [p["display"] for p in d["proposals"]] == ["10.05.2026"]  # проект — отдельно


def test_stn101_amount_from_signed_amendment_draft_separately():
    a = contract(run(base_files()), "STN-101")["amount"]
    assert a["value"] == 1_380_000 and a["base"]["value"] == 1_200_000
    assert [p["value"] for p in a["proposals"]] == [1_450_000]


def test_q2_stn102_amount_not_advance():
    a = contract(run(base_files()), "STN-102")["amount"]
    assert a["status"] == "ok" and a["value"] == 840_000       # не аванс 252 000
    assert a["evidence"]["file"] == "03_contract.txt" and a["evidence"]["para_label"] == "п. 2.1"


def test_q3_stn103_amount_no_data_not_budget_limit():
    a = contract(run(base_files()), "STN-103")["amount"]
    assert a["status"] == "no_data" and a["value"] is None     # не лимит 600 000
    assert "приложении № 1" in a["evidence"]["quote"]          # основание «нет данных»


def test_q4_before_april_and_unagreed_changes():
    res = run(base_files())
    early = [c["number"] for c in res["contracts"]
             if c["deadline"]["value"] and c["deadline"]["value"] < "2026-04-01"]
    assert early == ["STN-102"]
    d = contract(res, "STN-102")["deadline"]
    assert d["value"] == "2026-03-20"                          # не срок оплаты 10.04
    assert [(p["display"], p["doc"]) for p in d["proposals"]] == [("27.03.2026", "05_supplier_email.txt")]
    assert contract(res, "STN-103")["deadline"]["proposals"] == []


def test_suppliers_and_table_of_three():
    res = run(base_files())
    assert [(c["number"], c["supplier"]["value"]) for c in res["contracts"]] == [
        ("STN-101", "ООО «Вектор Прибор»"),
        ("STN-102", "ООО «Контур Электро»"),
        ("STN-103", "ООО «ПромСнаб Сервис»"),
    ]
    assert not any(c["needs_review"] for c in res["contracts"])
    assert res["unassigned"] == []


# --- проверяемость -------------------------------------------------------------

def test_every_quote_is_exact_substring_and_highlight_is_value():
    res = run(base_files())
    texts = {d["filename"]: d["text"] for d in res["documents"]}
    for c in res["contracts"]:
        for k in ("amount", "deadline"):
            ev = c[k]["evidence"]
            if ev is None:
                continue
            t = texts[ev["file"]]
            assert t[ev["start"]:ev["end"]] == ev["quote"]
            if c[k]["status"] == "ok":
                assert c[k]["display"].split(" ₽")[0] == t[ev["hl_start"]:ev["hl_end"]]


# --- независимость от имён и порядка файлов --------------------------------------

def test_filenames_and_order_do_not_matter():
    files = base_files()
    renamed = {f"z_{i}.txt": t for i, t in enumerate(reversed(list(files.values())))}
    a, b = run(files), run(renamed)
    pick = lambda r: [(c["number"], c["amount"]["value"], c["deadline"]["value"]) for c in r["contracts"]]
    assert pick(a) == pick(b)


# --- встреча: изменить поле, загрузить новый договор ------------------------------

def test_changed_field_is_picked_up():
    files = base_files()
    files["03_contract.txt"] = files["03_contract.txt"].replace(
        "840 000 (восемьсот сорок тысяч)", "910 000 (девятьсот десять тысяч)").replace(
        "не позднее 20.03.2026", "не позднее 25.03.2026")
    c = contract(run(files), "STN-102")
    assert c["amount"]["value"] == 910_000 and c["deadline"]["value"] == "2026-03-25"


NEW_CONTRACT = """ДОГОВОР ПОСТАВКИ № STN-104
Дата: 25.02.2026
Статус: подписан обеими сторонами 25.02.2026.

1.1. Покупатель: ООО «СеверМет». Поставщик: АО «Новый Поставщик».
1.2. Предмет: поставка кабельной продукции.

2.1. Общая стоимость поставки составляет 2 345 678,90 (два миллиона ...) рублей, включая НДС.

3.1. Поставщик обязуется поставить продукцию не позднее «28» марта 2026 г.
"""


def test_new_contract_same_format():
    files = base_files() | {"new.txt": NEW_CONTRACT}
    c = contract(run(files), "STN-104")
    assert c["supplier"]["value"] == "АО «Новый Поставщик»"
    assert c["amount"]["value"] == pytest.approx(2_345_678.90)
    assert c["deadline"]["value"] == "2026-03-28"


# --- статус документа -------------------------------------------------------------

def _amendment(status: str, effective: str = "05.03.2026", date_line="05.03.2026") -> str:
    return f"""ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № 1 К ДОГОВОРУ STN-103
Дата: {date_line}
Статус: {status}
Покупатель: ООО «СеверМет». Поставщик: ООО «ПромСнаб Сервис».

1. Пункт 3.1 договора изложить в следующей редакции: «Поставщик обязуется поставить запасные части не позднее 25.03.2026».

2. Настоящее соглашение вступает в силу {effective}.
"""


def test_signed_amendment_with_future_effective_date_not_applied():
    files = base_files() | {"x.txt": _amendment("подписано обеими сторонами 05.03.2026.", "15.03.2026")}
    d = contract(run(files), "STN-103")["deadline"]
    assert d["value"] == "2026-04-30" and d["status"] == "ok"
    assert d["proposals"][0]["display"] == "25.03.2026"
    assert "после даты проверки" in d["proposals"][0]["reason"]


def test_signed_effective_amendment_applied():
    files = base_files() | {"x.txt": _amendment("подписано обеими сторонами 05.03.2026.")}
    d = contract(run(files), "STN-103")["deadline"]
    assert d["value"] == "2026-03-25" and d["changed_by"].startswith("Доп. соглашение")


def test_signed_by_one_side_not_applied():
    files = base_files() | {"x.txt": _amendment("подписано поставщиком 05.03.2026.")}
    d = contract(run(files), "STN-103")["deadline"]
    assert d["value"] == "2026-04-30" and len(d["proposals"]) == 1


def test_unknown_status_needs_review():
    files = base_files() | {"x.txt": _amendment("на подписи у покупателя.")}
    c = contract(run(files), "STN-103")
    assert c["deadline"]["status"] == "needs_review" and c["needs_review"]
    assert c["deadline"]["value"] == "2026-04-30"   # действующее значение не подменяется


def test_signed_without_effective_date_needs_review():
    text = _amendment("подписано обеими сторонами 05.03.2026.").replace(
        "2. Настоящее соглашение вступает в силу 05.03.2026.", "")
    c = contract(run(base_files() | {"x.txt": text}), "STN-103")
    assert c["deadline"]["status"] == "needs_review"


def test_two_effective_amendments_same_date_conflict():
    a1 = _amendment("подписано обеими сторонами 05.03.2026.")
    a2 = a1.replace("25.03.2026", "26.03.2026").replace("№ 1", "№ 2")
    c = contract(run(base_files() | {"a1.txt": a1, "a2.txt": a2}), "STN-103")
    assert c["deadline"]["status"] == "needs_review"


def test_earlier_check_date_ignores_amendment():
    c = contract(run(base_files(), date(2026, 2, 28)), "STN-101")
    assert c["amount"]["value"] == 1_200_000 and c["deadline"]["value"] == "2026-04-15"
    assert c["amount"]["proposals"][0]["reason"].startswith("подписано 01.03.2026")


def test_amendment_without_contract_is_flagged():
    files = {"x.txt": _amendment("подписано обеими сторонами 05.03.2026.")}
    c = contract(run(files), "STN-103")
    assert c["needs_review"] and c["contract_file"] is None


def test_unrecognized_document_listed():
    res = run(base_files() | {"note.txt": "Заметки к совещанию\nобсудить сроки"})
    assert [u["file"] for u in res["unassigned"]] == ["note.txt"]


def test_cp1251_upload():
    files = base_files()
    raw = files.pop("03_contract.txt").encode("cp1251")
    res = analyze(list(files.items()) + [("03.txt", raw)], CHECK)
    assert contract(res, "STN-102")["amount"]["value"] == 840_000


def test_missing_amount_clause_is_no_data():
    files = base_files()
    files["03_contract.txt"] = "\n".join(
        l for l in files["03_contract.txt"].splitlines() if not l.startswith("2.1."))
    a = contract(run(files), "STN-102")["amount"]
    assert a["status"] == "no_data" and a["value"] is None
