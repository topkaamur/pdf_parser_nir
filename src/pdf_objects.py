"""Типы объектов PDF для внутреннего представления."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class PdfNull:
    """Объект PDF null."""

    def __repr__(self) -> str:
        return "null"


@dataclass
class PdfBoolean:
    """Логический объект PDF."""

    value: bool


@dataclass
class PdfInteger:
    """Целочисленный объект PDF."""

    value: int


@dataclass
class PdfReal:
    """Вещественный объект PDF."""

    value: float


@dataclass
class PdfString:
    """Литеральная строка PDF (в круглых скобках)."""

    value: bytes

    @property
    def text(self) -> str:
        try:
            if self.value.startswith(b"\xfe\xff"):
                return self.value[2:].decode("utf-16-be")
            return self.value.decode("latin-1")
        except (UnicodeDecodeError, ValueError):
            return self.value.decode("latin-1", errors="replace")


@dataclass
class PdfHexString:
    """Шестнадцатеричная строка PDF (в угловых скобках)."""

    value: bytes

    @property
    def text(self) -> str:
        try:
            if self.value.startswith(b"\xfe\xff"):
                return self.value[2:].decode("utf-16-be")
            return self.value.decode("latin-1")
        except (UnicodeDecodeError, ValueError):
            return self.value.decode("latin-1", errors="replace")


@dataclass
class PdfName:
    """Именованный объект PDF (начинается с /)."""

    name: str

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PdfName):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return NotImplemented


@dataclass
class PdfArray:
    """Массив PDF."""

    items: List[Any] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> Any:
        return self.items[index]

    def __iter__(self):
        return iter(self.items)


@dataclass
class PdfDict:
    """Словарь PDF."""

    entries: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.entries.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.entries[key]

    def __contains__(self, key: str) -> bool:
        return key in self.entries

    def __len__(self) -> int:
        return len(self.entries)

    def keys(self):
        return self.entries.keys()


@dataclass
class PdfStream:
    """Потоковый объект PDF (словарь + бинарные данные)."""

    dictionary: PdfDict
    raw_data: bytes = b""

    def get(self, key: str, default: Any = None) -> Any:
        return self.dictionary.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.dictionary


@dataclass
class PdfReference:
    """Косвенная ссылка на объект (например, 1 0 R)."""

    obj_num: int
    gen_num: int

    def __repr__(self) -> str:
        return f"{self.obj_num} {self.gen_num} R"

    def __hash__(self) -> int:
        return hash((self.obj_num, self.gen_num))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PdfReference):
            return self.obj_num == other.obj_num and self.gen_num == other.gen_num
        return NotImplemented


PdfObject = Union[
    PdfNull,
    PdfBoolean,
    PdfInteger,
    PdfReal,
    PdfString,
    PdfHexString,
    PdfName,
    PdfArray,
    PdfDict,
    PdfStream,
    PdfReference,
]
