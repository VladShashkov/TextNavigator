"""Извлечение полей из одного документа: поставщик, сумма, срок поставки.

Принцип: значение берётся только из целевой формулировки, а не из
«первого числа рядом со словом рублей». Поэтому лимит бюджета, аванс и
срок оплаты не попадают в сумму и срок поставки.

Чтобы добавить поле (например, ставку неустойки), достаточно написать
функцию `extract_<поле>(doc) -> list[Fact]` и зарегистрировать её в EXTRACTORS.
"""
from __future__ import annotations

import re
from typing import Callable

from .model import Document, Evidence, Fact
from .textutil import (AMOUNT_PATTERN, DATE_PATTERN, fmt_amount, fmt_date, parse_amount,
                       parse_date)

RUB = r"(?:рубл[а-я]*|руб\.?)"
WORDS = r"(?:\s*\([^)]*\))?"      # «(один миллион двести тысяч)»

# --- сумма -------------------------------------------------------------------
AMOUNT_RULES = [
    # договор / подписанное ДС: «Общая стоимость поставки составляет 1 200 000 (...) рублей»
    re.compile(r"[Оо]бщая\s+стоимость[^.;]{0,60}?\s+составляет\s+(" + AMOUNT_PATTERN + ")" + WORDS + r"\s*" + RUB),
    # проект / письмо: «изменить общую стоимость поставки на 1 450 000 рублей».
    # «увеличить/уменьшить на N» — это разница, а не новая сумма: см. RELATIVE_AMOUNT.
    re.compile(r"изменить\s+(?:общую\s+)?стоимость[^.;]{0,60}?\s+на\s+("
               + AMOUNT_PATTERN + ")" + WORDS + r"\s*" + RUB, re.I),
]
# «Общая стоимость» упомянута, но числа нет — фиксируем как «нет данных» с цитатой-объяснением
AMOUNT_MENTION = re.compile(r"[Оо]бщая\s+стоимость", re.I)
RELATIVE_AMOUNT = re.compile(r"(?:увеличить|уменьшить|увеличивается|уменьшается)[^.;]{0,60}?(?:стоимост|цен)[^.;]{0,40}?на\s+("
                             + AMOUNT_PATTERN + ")" + WORDS + r"\s*" + RUB, re.I)

# Упоминание поля без извлечённого значения в применяемом ДС → «требует проверки»
FIELD_MENTION = {
    "amount": re.compile(r"стоимост", re.I),
    "deadline": re.compile(r"срок\w*\s+поставки|обязуется\s+поставить", re.I),
}

# --- срок поставки -----------------------------------------------------------
DEADLINE_RULES = [
    # «обязуется поставить оборудование не позднее 15.04.2026»
    re.compile(r"обязуется\s+поставить[^.;]{0,80}?\s+не\s+позднее\s+(" + DATE_PATTERN + ")", re.I),
    # «Срок поставки — не позднее 15.04.2026» / «срок поставки: 15.04.2026»
    re.compile(r"[Сс]рок\s+поставки\s*(?:—|-|:|составляет)?\s*(?:не\s+позднее\s+)?(" + DATE_PATTERN + ")"),
    # проект: «изменить срок поставки на 10.05.2026»; письмо: «перенести срок поставки с 20.03.2026 на 27.03.2026»
    re.compile(r"(?:изменить|перенести)\s+срок\s+поставки(?:\s+с\s+" + DATE_PATTERN + r")?\s+на\s+("
               + DATE_PATTERN + ")", re.I),
]

SUPPLIER_RE = re.compile(r"Поставщик\s*:\s*([^.;\n]*?«[^»]+»)")
LETTER_FROM_RE = re.compile(r"^От\s*:\s*([^.;\n]*?«[^»]+»)")


def _facts(doc: Document, field: str, rules, convert, fmt) -> list[Fact]:
    out: list[Fact] = []
    for p in doc.paragraphs:
        for rule in rules:
            for m in rule.finditer(p.text):
                value = convert(m.group(1))
                if value is None:
                    continue
                ev = Evidence.of(doc, p, p.start + m.start(1), p.start + m.end(1))
                out.append(Fact(field, value, fmt(value), ev))
    return out


def extract_amount(doc: Document) -> list[Fact]:
    facts = _facts(doc, "amount", AMOUNT_RULES, parse_amount, fmt_amount)
    for p in doc.paragraphs:
        for m in RELATIVE_AMOUNT.finditer(p.text):
            ev = Evidence.of(doc, p, p.start + m.start(), p.start + m.end())
            facts.append(Fact("amount", None, f"изменение на {m.group(1)} ₽ (не итоговая сумма)", ev,
                              note="Относительное изменение стоимости — итоговую сумму нужно пересчитать вручную"))
    if not facts:
        # Пункт о стоимости есть, но числа в нём нет («определяется спецификацией»)
        for p in doc.paragraphs:
            if (m := AMOUNT_MENTION.search(p.text)) and not re.search(r"входит\s+в\s+общую", p.text, re.I):
                ev = Evidence.of(doc, p, p.start + m.start(), p.start + m.end())
                facts.append(Fact("amount", None, "нет данных", ev,
                                  note="Пункт о стоимости есть, но числового значения в нём нет"))
                break
    return facts


def extract_deadline(doc: Document) -> list[Fact]:
    return _facts(doc, "deadline", DEADLINE_RULES, parse_date, fmt_date)


def extract_supplier(doc: Document) -> list[Fact]:
    facts = _facts(doc, "supplier", [SUPPLIER_RE], str.strip, str)
    if not facts and doc.kind == "letter":
        facts = _facts(doc, "supplier", [LETTER_FROM_RE], str.strip, str)
    return facts[:1]


EXTRACTORS: dict[str, Callable[[Document], list[Fact]]] = {
    "supplier": extract_supplier,
    "amount": extract_amount,
    "deadline": extract_deadline,
}


def extract_all(doc: Document) -> list[Fact]:
    facts: list[Fact] = []
    for fn in EXTRACTORS.values():
        facts.extend(fn(doc))
    return facts
