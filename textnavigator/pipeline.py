"""Точка входа ядра: файлы → документы → результат по договорам → JSON."""
from __future__ import annotations

from datetime import date

from .model import NO_DATA, OK, REVIEW, ContractResult, Document, Evidence, to_json
from .parser import parse_document
from .resolver import resolve


def validate(results: list[ContractResult], docs: dict[str, Document]) -> list[str]:
    """Инварианты проверяемости (аналог хука validate_report в Штольце).

    1. Каждая цитата — точная подстрока исходного файла по сохранённым смещениям.
    2. Выделенный фрагмент лежит внутри абзаца-цитаты.
    3. «ok» всегда с основанием; «нет данных» — без значения.
    """
    errors: list[str] = []

    def check_ev(ev: Evidence | dict | None, where: str):
        if ev is None:
            return
        e = ev if isinstance(ev, Evidence) else Evidence(**ev)
        doc = docs.get(e.file)
        if doc is None:
            errors.append(f"{where}: файл {e.file} не загружен")
        elif doc.text[e.start:e.end] != e.quote:
            errors.append(f"{where}: цитата не совпадает с текстом {e.file}")
        elif not (e.start <= e.hl_start <= e.hl_end <= e.end):
            errors.append(f"{where}: выделение вне абзаца")

    for r in results:
        for name in ("supplier", "amount", "deadline"):
            f = getattr(r, name)
            where = f"{r.number}.{name}"
            if f.status == OK and (f.value is None or f.evidence is None):
                errors.append(f"{where}: значение без основания")
            if f.status == NO_DATA and f.value is not None:
                errors.append(f"{where}: «нет данных» со значением")
            check_ev(f.evidence, where)
            for h in f.history:
                check_ev(h["evidence"], where + ".history")
            for p in f.proposals:
                check_ev(p.evidence, where + ".proposal")
    return errors


def analyze(files: list[tuple[str, bytes | str]], check: date) -> dict:
    docs = [parse_document(name, raw) for name, raw in files]
    by_name = {d.filename: d for d in docs}
    if len(by_name) != len(docs):
        # одинаковые имена — смещения цитат стали бы неоднозначными
        raise ValueError("Загружены файлы с одинаковыми именами")
    results, unassigned = resolve(docs, check)
    errors = validate(results, by_name)
    if errors:
        # Безопасный отказ: нарушение инварианта переводит договор в «требует проверки».
        for r in results:
            mine = [e for e in errors if e.startswith(r.number + ".")]
            if mine:
                r.issues.extend("Внутренняя проверка: " + e for e in mine)
                for name in ("supplier", "amount", "deadline"):
                    getattr(r, name).status = REVIEW
    return {
        "check_date": check.isoformat(),
        "contracts": to_json(results),
        "unassigned": unassigned,
        "documents": [
            {"filename": d.filename, "title": d.title, "kind": d.kind,
             "contract_no": d.contract_no, "status": d.status, "status_text": d.status_text,
             "text": d.text, "paragraphs": to_json(d.paragraphs)}
            for d in docs
        ],
        "validation_errors": errors,
    }
