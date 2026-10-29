"""Сведение документов по договору на дату проверки.

Правило задания: условия изменяет только допсоглашение, подписанное обеими
сторонами и вступившее в силу к дате проверки. Всё остальное (проект,
письмо, ДС, вступающее позже) показывается отдельно как предложение.
Если ситуацию нельзя разрешить надёжно — статус «требует проверки».
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from .model import (AMENDMENT, CONTRACT, LETTER, NO_DATA, OK, REVIEW, SIGNED, STATUS_UNKNOWN,
                    UNSIGNED, ContractResult, Document, Fact, FieldResult, Proposal)
from .textutil import fmt_date

FIELDS = ("supplier", "amount", "deadline")
FIELD_NAMES = {"supplier": "поставщик", "amount": "сумма", "deadline": "срок поставки"}


def _natural_key(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def amendment_applicability(doc: Document, check: date) -> tuple[bool, str, bool]:
    """(применяется?, причина, требует ли проверки)."""
    if doc.kind == LETTER:
        return False, "письмо — предложение, а не изменение договора", False
    if doc.status == UNSIGNED:
        return False, f"не подписано обеими сторонами ({doc.status_text})", False
    if doc.status == STATUS_UNKNOWN:
        return False, f"статус подписания не определён ({doc.status_text})", True
    # SIGNED
    if doc.signed_date and doc.signed_date > check:
        return False, f"подписано {fmt_date(doc.signed_date)} — после даты проверки", False
    if doc.effective_date is None:
        return False, "подписано, но дата вступления в силу в тексте не найдена", True
    if doc.effective_date > check:
        return False, f"вступает в силу {fmt_date(doc.effective_date)} — после даты проверки", False
    return True, f"подписано и вступило в силу {fmt_date(doc.effective_date)}", False


def _single(facts: list[Fact], who: str) -> tuple[Fact | None, str | None]:
    """Одно значение из документа или причина неоднозначности."""
    if not facts:
        return None, None
    values = {f.display for f in facts}
    if len(values) > 1:
        return None, f"{who}: найдено несколько разных значений ({', '.join(sorted(values))})"
    return facts[0], None


def _field_from_contract(contract: Document | None, field: str) -> FieldResult:
    if contract is None:
        return FieldResult(REVIEW, notes=["Договор не загружен — исходное значение неизвестно"])
    facts = [f for f in contract.facts if f.field == field]
    fact, err = _single(facts, contract.filename)
    if err:
        return FieldResult(REVIEW, notes=[err])
    if fact is None:
        return FieldResult(NO_DATA, notes=[f"В тексте договора {FIELD_NAMES[field]} не найден(а)"])
    if fact.value is None:
        return FieldResult(NO_DATA, evidence=fact.evidence, notes=[fact.note])
    r = FieldResult(OK, fact.value, fact.display, fact.evidence)
    r.base = {"value": fact.value, "display": fact.display, "evidence": fact.evidence}
    r.history.append({"display": fact.display, "doc": contract.label(), "evidence": fact.evidence})
    return r


def resolve(docs: list[Document], check: date) -> tuple[list[ContractResult], list[dict]]:
    groups: dict[str, list[Document]] = defaultdict(list)
    unassigned: list[dict] = []
    for d in docs:
        if d.contract_no:
            groups[d.contract_no].append(d)
        else:
            unassigned.append({"file": d.filename, "title": d.title, "kind": d.kind,
                               "problems": d.problems or ["Не удалось связать с договором"]})

    results = [_resolve_one(no, groups[no], check) for no in sorted(groups, key=_natural_key)]
    return results, unassigned


def _resolve_one(number: str, docs: list[Document], check: date) -> ContractResult:
    issues: list[str] = []
    contracts = [d for d in docs if d.kind == CONTRACT]
    changes = [d for d in docs if d.kind in (AMENDMENT, LETTER)]
    contract = contracts[0] if contracts else None

    if not contracts:
        issues.append("Текст договора не загружен — есть только связанные документы")
    if len(contracts) > 1:
        issues.append("Несколько документов с этим номером договора: "
                      + ", ".join(c.filename for c in contracts))
    if contract:
        if contract.status != SIGNED:
            issues.append(f"Договор не подписан обеими сторонами: {contract.status_text}")
        elif contract.signed_date and contract.signed_date > check:
            issues.append(f"Договор подписан {fmt_date(contract.signed_date)} — после даты проверки")
    for d in docs:
        issues.extend(f"{d.filename}: {p}" for p in d.problems)

    fields = {f: _field_from_contract(contract, f) for f in FIELDS}
    if len(contracts) > 1:
        for f in FIELDS:
            fields[f].status = REVIEW

    doc_rows = []
    if contract:
        doc_rows.append({"file": contract.filename, "title": contract.title, "kind": CONTRACT,
                         "status_text": contract.status_text, "role": "основной документ",
                         "applied": True})

    # Порядок применения — по дате вступления в силу, а не по имени файла/загрузке.
    def order(d: Document):
        return (d.effective_date or date.max, d.signed_date or date.max, d.filename)

    for d in sorted(changes, key=order):
        applied, reason, review = amendment_applicability(d, check)
        doc_rows.append({"file": d.filename, "title": d.title, "kind": d.kind,
                         "status_text": d.status_text, "role": reason, "applied": applied})
        if review:
            issues.append(f"{d.label()}: {reason}")
        for f in FIELDS:
            facts = [x for x in d.facts if x.field == f]
            if not facts:
                continue
            r = fields[f]
            if f == "supplier":
                # Поставщик из ДС/письма не «изменение», а сверка: не совпал — проверить.
                if r.value and facts[0].value != r.value:
                    issues.append(f"{d.label()}: поставщик «{facts[0].value}» не совпадает с договором")
                if r.value is None and contract is None:
                    fields[f] = FieldResult(REVIEW, facts[0].value, facts[0].display, facts[0].evidence,
                                            notes=["Взято из связанного документа, договор не загружен"])
                continue
            fact, err = _single(facts, d.filename)
            if err:
                r.status = REVIEW
                r.notes.append(err)
                continue
            if fact.value is None:
                if applied:
                    r.status = REVIEW
                    r.notes.append(f"{d.label()} меняет пункт о стоимости, но числа нет")
                continue
            if applied:
                r.history.append({"display": fact.display, "doc": d.label(), "evidence": fact.evidence})
                r.value, r.display, r.evidence = fact.value, fact.display, fact.evidence
                r.changed_by = d.label()
                if r.status == NO_DATA:
                    r.status = OK
                if contract is None:
                    r.status = REVIEW
            else:
                r.proposals.append(Proposal(fact.value, fact.display, d.filename, d.title,
                                            reason, fact.evidence))
                if review:
                    r.status = REVIEW
                    r.notes.append(f"Есть документ с неопределённым статусом: {d.label()}")

    # Два применённых ДС с одной датой вступления, меняющие одно поле по-разному
    for f in ("amount", "deadline"):
        applied_docs = [d for d in changes if amendment_applicability(d, check)[0]
                        and any(x.field == f and x.value is not None for x in d.facts)]
        by_date = defaultdict(set)
        for d in applied_docs:
            by_date[d.effective_date].update(x.display for x in d.facts if x.field == f)
        for eff, vals in by_date.items():
            if len(vals) > 1:
                fields[f].status = REVIEW
                fields[f].notes.append(
                    f"Несколько ДС вступили в силу {fmt_date(eff)} с разными значениями: {', '.join(sorted(vals))}")

    if fields["deadline"].value is None and fields["deadline"].status == OK:
        fields["deadline"].status = NO_DATA

    return ContractResult(number, contract.filename if contract else None,
                          fields["supplier"], fields["amount"], fields["deadline"],
                          doc_rows, issues)
