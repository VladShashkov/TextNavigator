"""Низкоуровневые утилиты: декодирование, абзацы, даты, суммы.

Всё детерминированно; смещения считаются по нормализованному тексту,
который же показывается пользователю — поэтому цитата всегда является
точной подстрокой отображаемого документа.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# --- декодирование -----------------------------------------------------------

def decode(raw: bytes) -> str:
    """UTF-8 (в т.ч. с BOM), иначе cp1251. Переводы строк → \\n, NBSP → пробел."""
    for enc in ("utf-8-sig", "cp1251"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - cp1251 декодирует любые байты
        text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")


# --- абзацы ------------------------------------------------------------------

CLAUSE_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.\s")


@dataclass
class Paragraph:
    id: str          # стабильный id для перехода: p<номер строки>
    line: int        # номер строки (с 1)
    start: int       # смещение начала в тексте документа
    end: int         # смещение конца
    text: str
    clause: str | None  # номер пункта договора, если есть («2.1»)

    def label(self) -> str:
        return f"п. {self.clause}" if self.clause else f"строка {self.line}"


def split_paragraphs(text: str) -> list[Paragraph]:
    """Абзац = непустая строка. В учебном формате каждый пункт — своя строка."""
    paras: list[Paragraph] = []
    pos = 0
    for i, line in enumerate(text.split("\n"), start=1):
        start, end = pos, pos + len(line)
        pos = end + 1
        stripped = line.strip()
        if not stripped:
            continue
        lead = len(line) - len(line.lstrip())
        trail = len(line) - len(line.rstrip())
        m = CLAUSE_RE.match(line)
        paras.append(Paragraph(
            id=f"p{i}", line=i, start=start + lead, end=end - trail,
            text=stripped, clause=m.group(1) if m else None,
        ))
    return paras


# --- даты --------------------------------------------------------------------

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
# 15.04.2026 | «15» апреля 2026 г. | 15 апреля 2026
DATE_PATTERN = (
    r"(?:\d{1,2}\.\d{1,2}\.\d{4}"
    r"|«?\d{1,2}»?\s+(?:" + "|".join(MONTHS) + r")\s+\d{4}(?:\s*г\.?)?)"
)
DATE_RE = re.compile(DATE_PATTERN, re.IGNORECASE)


def parse_date(s: str) -> date | None:
    s = s.strip()
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        d, mo, y = map(int, m.groups())
    else:
        m = re.fullmatch(r"«?(\d{1,2})»?\s+([а-я]+)\s+(\d{4})(?:\s*г\.?)?", s, re.IGNORECASE)
        if not m or m.group(2).lower() not in MONTHS:
            return None
        d, mo, y = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
    try:
        return date(y, mo, d)
    except ValueError:
        return None  # 31.02.2026 — не дата, а повод для проверки


def fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


# --- суммы -------------------------------------------------------------------

# 1 200 000 | 1200000 | 1 200 000,50 ; пробелы-разделители тысяч
AMOUNT_PATTERN = r"\d{1,3}(?:[  ]\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?"


def parse_amount(s: str) -> float:
    return float(re.sub(r"[  ]", "", s).replace(",", "."))


def fmt_amount(v: float) -> str:
    whole = int(v)
    s = f"{whole:,}".replace(",", " ")
    if abs(v - whole) > 1e-9:
        s += f",{round((v - whole) * 100):02d}"
    return s + " ₽"
