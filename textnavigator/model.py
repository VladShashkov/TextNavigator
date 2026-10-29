"""Структуры данных. Всё сериализуется в JSON для интерфейса."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from .textutil import Paragraph

# Тип документа
CONTRACT, AMENDMENT, LETTER, UNKNOWN = "contract", "amendment", "letter", "unknown"

# Юридический статус документа на дату проверки
SIGNED = "signed"            # подписан обеими сторонами
UNSIGNED = "unsigned"        # проект / не подписан / подписан не всеми
PROPOSAL = "proposal"        # письмо — всегда только предложение
STATUS_UNKNOWN = "unknown"   # статус не удалось определить → проверка

# Статус значения поля
OK, NO_DATA, REVIEW = "ok", "no_data", "needs_review"


@dataclass
class Evidence:
    """Проверяемое основание: файл, абзац, точная цитата и выделенный фрагмент."""
    file: str
    para_id: str
    para_label: str
    quote: str          # полный текст абзаца (точная подстрока документа)
    start: int          # смещение абзаца в документе
    end: int
    hl_start: int       # выделенный фрагмент внутри документа (значение)
    hl_end: int

    @classmethod
    def of(cls, doc: "Document", para: Paragraph, hl_start: int, hl_end: int) -> "Evidence":
        return cls(doc.filename, para.id, para.label(), para.text,
                   para.start, para.end, hl_start, hl_end)


@dataclass
class Fact:
    """Значение, извлечённое из одного документа."""
    field: str                  # supplier | amount | deadline
    value: Any                  # str | float | date | None (None = в тексте сказано, что значения нет)
    display: str
    evidence: Evidence
    note: str = ""


@dataclass
class Document:
    filename: str
    text: str
    paragraphs: list[Paragraph]
    kind: str = UNKNOWN
    title: str = ""                       # «Дополнительное соглашение № 1»
    contract_no: str | None = None
    status: str = STATUS_UNKNOWN
    status_text: str = ""                 # человекочитаемо
    status_evidence: Evidence | None = None
    signed_date: date | None = None
    effective_date: date | None = None
    effective_evidence: Evidence | None = None
    facts: list[Fact] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def label(self) -> str:
        return f"{self.title or self.filename} ({self.filename})"


@dataclass
class Proposal:
    """Изменение, которое на дату проверки условия не меняет."""
    value: Any
    display: str
    doc: str
    doc_title: str
    reason: str          # почему не применено
    evidence: Evidence


@dataclass
class FieldResult:
    status: str                         # ok | no_data | needs_review
    value: Any = None
    display: str = "нет данных"
    evidence: Evidence | None = None
    changed_by: str | None = None       # каким документом изменено
    base: dict | None = None            # исходное значение по договору
    history: list[dict] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ContractResult:
    number: str
    contract_file: str | None
    supplier: FieldResult
    amount: FieldResult
    deadline: FieldResult
    documents: list[dict]       # связанные документы и как они учтены
    issues: list[str]           # причины «требует проверки» на уровне договора

    @property
    def needs_review(self) -> bool:
        return bool(self.issues) or any(
            f.status == REVIEW for f in (self.supplier, self.amount, self.deadline))


def to_json(obj: Any) -> Any:
    """Рекурсивная сериализация dataclass/date для Flask."""
    if hasattr(obj, "__dataclass_fields__"):
        d = {k: to_json(v) for k, v in asdict(obj).items()}
        if isinstance(obj, ContractResult):
            d["needs_review"] = obj.needs_review
        return d
    if isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj
