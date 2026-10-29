"""Классификация документа: тип, номер договора, статус подписания, дата вступления в силу.

Решения принимаются только по тексту документа. Имя файла и порядок загрузки
не используются (требование задания).
"""
from __future__ import annotations

import re

from . import extractors
from .model import (AMENDMENT, CONTRACT, LETTER, PROPOSAL, SIGNED, STATUS_UNKNOWN,
                    UNKNOWN, UNSIGNED, Document, Evidence)
from .textutil import DATE_PATTERN, decode, parse_date, split_paragraphs

# Номер договора: «STN-101», «ПС-2026/15» и т.п.
CONTRACT_NO = r"([A-ZА-ЯЁ]{1,10}-?[\w/-]*\d[\w/-]*)"

HEAD_CONTRACT = re.compile(r"^ДОГОВОР(?:\s+ПОСТАВКИ)?\s*№\s*" + CONTRACT_NO, re.I)
HEAD_AMENDMENT = re.compile(
    r"^(ПРОЕКТ\s+)?ДОПОЛНИТЕЛЬНО[ЕГО]+\s+СОГЛАШЕНИ[ЕЯ]\s*(?:№\s*(\S+))?\s+К\s+ДОГОВОРУ"
    r"(?:\s+ПОСТАВКИ)?\s*(?:№\s*)?" + CONTRACT_NO, re.I)
HEAD_LETTER = re.compile(r"^ПИСЬМО\b", re.I)
LETTER_REF = re.compile(r"договор[а-я]*(?:\s+поставки)?\s*(?:№\s*)?" + CONTRACT_NO, re.I)

STATUS_LINE = re.compile(r"^Статус\s*:\s*(.+)$", re.I)
SIGNED_BOTH = re.compile(r"подписан[оа]?\s+обеими\s+сторонами(?:\s+(" + DATE_PATTERN + "))?", re.I)
ONE_SIDE = re.compile(r"\bподписан[оа]?\s+(?:только\s+)?(?:поставщиком|покупателем|одной\s+стороной)", re.I)
NOT_SIGNED = re.compile(r"\bне\s+подписан|\bпроект\b", re.I)
EFFECTIVE = re.compile(r"вступает\s+в\s+силу\s+(?:с\s+)?(" + DATE_PATTERN + ")", re.I)
DOC_DATE = re.compile(r"^Дата(?:\s+проекта)?\s*:\s*(" + DATE_PATTERN + ")", re.I)


def parse_document(filename: str, raw: bytes | str) -> Document:
    text = raw if isinstance(raw, str) else decode(raw)
    doc = Document(filename=filename, text=text, paragraphs=split_paragraphs(text))
    if not doc.paragraphs:
        doc.problems.append("Пустой файл")
        return doc

    head = doc.paragraphs[0].text
    if m := HEAD_AMENDMENT.match(head):
        doc.kind = AMENDMENT
        doc.contract_no = m.group(3).upper()
        num = f" № {m.group(2)}" if m.group(2) else ""
        doc.title = ("Проект доп. соглашения" if m.group(1) else "Доп. соглашение") + num
        if m.group(1):
            doc.status, doc.status_text = UNSIGNED, "проект (по заголовку)"
    elif m := HEAD_CONTRACT.match(head):
        doc.kind = CONTRACT
        doc.contract_no = m.group(1).upper()
        doc.title = f"Договор {doc.contract_no}"
    elif HEAD_LETTER.match(head) or _looks_like_letter(doc):
        doc.kind = LETTER
        doc.title = "Письмо"
        for p in doc.paragraphs:
            if m := LETTER_REF.search(p.text):
                doc.contract_no = m.group(1).upper()
                break
        doc.status, doc.status_text = PROPOSAL, "письмо — не изменяет условия"
    else:
        doc.problems.append("Не удалось определить тип документа по заголовку")

    _parse_status(doc)
    doc.facts = extractors.extract_all(doc)
    if doc.kind != UNKNOWN and not doc.contract_no:
        doc.problems.append("Не найден номер договора")
    return doc


def _looks_like_letter(doc: Document) -> bool:
    heads = {p.text.split(":")[0].strip().lower() for p in doc.paragraphs[:8] if ":" in p.text}
    return {"от", "кому"} <= heads


def _parse_status(doc: Document) -> None:
    draft_by_title = doc.status == UNSIGNED
    for p in doc.paragraphs:
        if (m := STATUS_LINE.match(p.text)) and doc.kind != LETTER:
            st = m.group(1)
            sm = SIGNED_BOTH.search(st)
            if draft_by_title and sm and not NOT_SIGNED.search(st):
                doc.status, doc.status_text = STATUS_UNKNOWN, st.rstrip(".")
                doc.problems.append("Заголовок «проект», а статус «подписан» — противоречие")
            elif NOT_SIGNED.search(st):
                doc.status, doc.status_text = UNSIGNED, st.rstrip(".")
            elif sm:
                doc.status, doc.status_text = SIGNED, st.rstrip(".")
                if sm.group(1):
                    doc.signed_date = parse_date(sm.group(1))
            elif ONE_SIDE.search(st):
                # «подписан поставщиком» — не обеими сторонами. Простое вхождение
                # «подписан» не годится: «направлено на подписание» ≠ подписано.
                doc.status, doc.status_text = UNSIGNED, st.rstrip(".") + " (не обеими сторонами)"
            else:
                doc.status, doc.status_text = STATUS_UNKNOWN, st.rstrip(".")
            doc.status_evidence = Evidence.of(doc, p, p.start + m.start(1), p.start + m.end(1))
        if doc.kind == AMENDMENT and (m := EFFECTIVE.search(p.text)):
            d = parse_date(m.group(1))
            if d:
                doc.effective_date = d
                doc.effective_evidence = Evidence.of(doc, p, p.start + m.start(1), p.start + m.end(1))
    if doc.kind in (CONTRACT, AMENDMENT) and doc.status_evidence is None and doc.status == STATUS_UNKNOWN:
        doc.status_text = "статус подписания в тексте не указан"
