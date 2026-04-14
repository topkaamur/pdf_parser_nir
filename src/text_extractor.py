"""Извлечение текста из контентных потоков PDF.

Разбирает операторы контентного потока страницы PDF для извлечения
текста с позиционной информацией и данными о шрифте.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .models import TextBlock
from .pdf_objects import (
    PdfArray,
    PdfDict,
    PdfHexString,
    PdfInteger,
    PdfName,
    PdfReal,
    PdfReference,
    PdfStream,
    PdfString,
)

STANDARD_ENCODINGS = {
    "StandardEncoding": {i: chr(i) for i in range(256)},
    "WinAnsiEncoding": {i: chr(i) if i < 128 else chr(i) for i in range(256)},
    "MacRomanEncoding": {i: chr(i) for i in range(256)},
}


def parse_tounicode_cmap(cmap_data: bytes) -> Dict[int, str]:
    """Разобрать поток ToUnicode CMap в таблицу код_символа -> юникод."""
    mapping: Dict[int, str] = {}
    text = cmap_data.decode("latin-1", errors="replace")

    bfchar_pattern = re.compile(
        r"beginbfchar\s*(.*?)\s*endbfchar", re.DOTALL
    )
    for m in bfchar_pattern.finditer(text):
        block = m.group(1).strip()
        pairs = re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block)
        for src_hex, dst_hex in pairs:
            src_code = int(src_hex, 16)
            dst_bytes = bytes.fromhex(dst_hex)
            try:
                dst_str = dst_bytes.decode("utf-16-be")
            except (UnicodeDecodeError, ValueError):
                dst_str = dst_bytes.decode("latin-1", errors="replace")
            mapping[src_code] = dst_str

    bfrange_pattern = re.compile(
        r"beginbfrange\s*(.*?)\s*endbfrange", re.DOTALL
    )
    for m in bfrange_pattern.finditer(text):
        block = m.group(1).strip()
        ranges = re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block
        )
        for start_hex, end_hex, dst_hex in ranges:
            start = int(start_hex, 16)
            end = int(end_hex, 16)
            dst_start_bytes = bytes.fromhex(dst_hex)
            try:
                dst_start_code = int.from_bytes(dst_start_bytes, "big")
            except ValueError:
                continue
            for i in range(end - start + 1):
                code_point = dst_start_code + i
                try:
                    mapping[start + i] = chr(code_point)
                except (ValueError, OverflowError):
                    pass

    return mapping


@dataclass
class TextState:
    """Текущее состояние рендеринга текста."""

    font_name: str = ""
    font_size: float = 0.0
    char_spacing: float = 0.0
    word_spacing: float = 0.0
    leading: float = 0.0
    rise: float = 0.0
    matrix: List[float] = field(default_factory=lambda: [1, 0, 0, 1, 0, 0])
    line_matrix: List[float] = field(default_factory=lambda: [1, 0, 0, 1, 0, 0])

    @property
    def x(self) -> float:
        return self.matrix[4]

    @property
    def y(self) -> float:
        return self.matrix[5]

    def set_matrix(self, a: float, b: float, c: float, d: float, e: float, f: float):
        self.matrix = [a, b, c, d, e, f]
        self.line_matrix = [a, b, c, d, e, f]

    def translate(self, tx: float, ty: float):
        self.line_matrix[4] += tx * self.line_matrix[0] + ty * self.line_matrix[2]
        self.line_matrix[5] += tx * self.line_matrix[1] + ty * self.line_matrix[3]
        self.matrix = self.line_matrix.copy()

    def newline(self):
        self.translate(0, -self.leading)


class ContentStreamTokenizer:
    """Токенизатор операторов контентного потока PDF."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    @property
    def at_end(self) -> bool:
        return self.pos >= len(self.data)

    def skip_whitespace(self):
        while self.pos < len(self.data) and self.data[self.pos] in b" \t\n\r":
            self.pos += 1

    def read_token(self) -> Optional[str]:
        self.skip_whitespace()
        if self.at_end:
            return None

        ch = self.data[self.pos]

        if ch == ord("("):
            return self._read_string()
        if ch == ord("<"):
            if self.pos + 1 < len(self.data) and self.data[self.pos + 1] == ord("<"):
                return self._read_dict_marker()
            return self._read_hex_string()
        if ch == ord(">") and self.pos + 1 < len(self.data) and self.data[self.pos + 1] == ord(">"):
            self.pos += 2
            return ">>"
        if ch == ord("["):
            self.pos += 1
            return "["
        if ch == ord("]"):
            self.pos += 1
            return "]"
        if ch == ord("/"):
            return self._read_name()

        start = self.pos
        while self.pos < len(self.data) and self.data[self.pos] not in b" \t\n\r()[]<>/":
            self.pos += 1
        return self.data[start:self.pos].decode("latin-1")

    def _read_string(self) -> str:
        self.pos += 1
        result = []
        depth = 1
        while self.pos < len(self.data) and depth > 0:
            ch = self.data[self.pos]
            if ch == ord("\\"):
                self.pos += 1
                if self.pos < len(self.data):
                    esc = self.data[self.pos]
                    if esc == ord("n"):
                        result.append("\n")
                    elif esc == ord("r"):
                        result.append("\r")
                    elif esc == ord("t"):
                        result.append("\t")
                    elif esc in (ord("("), ord(")"), ord("\\")):
                        result.append(chr(esc))
                    elif ord("0") <= esc <= ord("7"):
                        octal = chr(esc)
                        for _ in range(2):
                            if self.pos + 1 < len(self.data) and ord("0") <= self.data[self.pos + 1] <= ord("7"):
                                self.pos += 1
                                octal += chr(self.data[self.pos])
                            else:
                                break
                        result.append(chr(int(octal, 8) & 0xFF))
                    else:
                        result.append(chr(esc))
            elif ch == ord("("):
                depth += 1
                result.append("(")
            elif ch == ord(")"):
                depth -= 1
                if depth > 0:
                    result.append(")")
            else:
                result.append(chr(ch))
            self.pos += 1
        return "(" + "".join(result) + ")"

    def _read_hex_string(self) -> str:
        start = self.pos
        self.pos += 1
        while self.pos < len(self.data) and self.data[self.pos] != ord(">"):
            self.pos += 1
        if self.pos < len(self.data):
            self.pos += 1
        return self.data[start:self.pos].decode("latin-1")

    def _read_dict_marker(self) -> str:
        self.pos += 2
        return "<<"

    def _read_name(self) -> str:
        start = self.pos
        self.pos += 1
        while self.pos < len(self.data) and self.data[self.pos] not in b" \t\n\r()[]<>/{}/":
            self.pos += 1
        return self.data[start:self.pos].decode("latin-1")


# Графические операторы PDF, которые игнорируются при извлечении текста
_GRAPHICS_STATE_OPS = frozenset({
    "k", "K", "g", "G", "rg", "RG",
    "cs", "CS", "sc", "SC", "scn", "SCN",
    "q", "Q", "cm", "w", "J", "j", "M", "d", "ri", "i", "gs",
    "W", "W*", "n",
    "m", "l", "c", "v", "y", "h", "re",
    "S", "s", "f", "F", "f*", "B", "B*", "b", "b*",
    "Do",
})


class TextExtractor:
    """Извлекает текстовые блоки из данных контентного потока PDF."""

    def __init__(
        self,
        font_map: Optional[Dict[str, Any]] = None,
        tounicode_maps: Optional[Dict[str, Dict[int, str]]] = None,
    ):
        self.font_map = font_map or {}
        self.tounicode_maps: Dict[str, Dict[int, str]] = tounicode_maps or {}
        self.encoding_cache: Dict[str, Dict[int, str]] = {}

    def extract(self, content_data: bytes) -> List[TextBlock]:
        """Извлечь текстовые блоки из байтов контентного потока."""
        if not content_data:
            return []

        blocks: List[TextBlock] = []
        state = TextState()
        stack: List[str] = []
        tokenizer = ContentStreamTokenizer(content_data)
        in_text = False

        while not tokenizer.at_end:
            token = tokenizer.read_token()
            if token is None:
                break

            if token == "BT":
                in_text = True
                state = TextState()
                stack = []
                continue
            elif token == "ET":
                in_text = False
                stack = []
                continue

            if not in_text:
                stack = []
                continue

            if token == "Tf":
                if len(stack) >= 2:
                    font_name = stack[-2]
                    if font_name.startswith("/"):
                        font_name = font_name[1:]
                    try:
                        state.font_size = float(stack[-1])
                    except ValueError:
                        pass
                    state.font_name = font_name
                stack = []
            elif token == "Td":
                if len(stack) >= 2:
                    try:
                        tx = float(stack[-2])
                        ty = float(stack[-1])
                        state.translate(tx, ty)
                    except ValueError:
                        pass
                stack = []
            elif token == "TD":
                if len(stack) >= 2:
                    try:
                        tx = float(stack[-2])
                        ty = float(stack[-1])
                        state.leading = -ty
                        state.translate(tx, ty)
                    except ValueError:
                        pass
                stack = []
            elif token == "Tm":
                if len(stack) >= 6:
                    try:
                        vals = [float(v) for v in stack[-6:]]
                        state.set_matrix(*vals)
                    except ValueError:
                        pass
                stack = []
            elif token == "T*":
                state.newline()
                stack = []
            elif token == "Tc":
                if stack:
                    try:
                        state.char_spacing = float(stack[-1])
                    except ValueError:
                        pass
                stack = []
            elif token == "Tw":
                if stack:
                    try:
                        state.word_spacing = float(stack[-1])
                    except ValueError:
                        pass
                stack = []
            elif token == "TL":
                if stack:
                    try:
                        state.leading = float(stack[-1])
                    except ValueError:
                        pass
                stack = []
            elif token == "Ts":
                if stack:
                    try:
                        state.rise = float(stack[-1])
                    except ValueError:
                        pass
                stack = []
            elif token == "Tj":
                if stack:
                    text = self._decode_string(stack[-1], state.font_name)
                    if text:
                        blocks.append(TextBlock(
                            text=text,
                            x=state.x,
                            y=state.y + state.rise,
                            font_name=state.font_name,
                            font_size=state.font_size,
                        ))
                stack = []
            elif token == "TJ":
                text = self._process_tj_array(stack, state.font_name)
                if text:
                    blocks.append(TextBlock(
                        text=text,
                        x=state.x,
                        y=state.y + state.rise,
                        font_name=state.font_name,
                        font_size=state.font_size,
                    ))
                stack = []
            elif token == "'":
                state.newline()
                if stack:
                    text = self._decode_string(stack[-1], state.font_name)
                    if text:
                        blocks.append(TextBlock(
                            text=text,
                            x=state.x,
                            y=state.y + state.rise,
                            font_name=state.font_name,
                            font_size=state.font_size,
                        ))
                stack = []
            elif token == '"':
                if len(stack) >= 3:
                    try:
                        state.word_spacing = float(stack[-3])
                        state.char_spacing = float(stack[-2])
                    except ValueError:
                        pass
                    state.newline()
                    text = self._decode_string(stack[-1], state.font_name)
                    if text:
                        blocks.append(TextBlock(
                            text=text,
                            x=state.x,
                            y=state.y + state.rise,
                            font_name=state.font_name,
                            font_size=state.font_size,
                        ))
                stack = []
            elif token in _GRAPHICS_STATE_OPS:
                stack = []
            else:
                stack.append(token)

        return blocks

    def _apply_tounicode(self, raw_bytes: bytes, font_name: str) -> Optional[str]:
        """Применить маппинг ToUnicode, если доступен для данного шрифта."""
        umap = self.tounicode_maps.get(font_name)
        if umap is None:
            return None
        chars: List[str] = []
        for b in raw_bytes:
            mapped = umap.get(b)
            if mapped is not None:
                chars.append(mapped)
            else:
                chars.append(chr(b))
        return "".join(chars)

    def _decode_string(self, raw: str, font_name: str) -> str:
        """Декодировать строковый токен PDF в строку Python."""
        if raw.startswith("(") and raw.endswith(")"):
            inner = raw[1:-1]
            raw_bytes = inner.encode("latin-1", errors="replace")
            mapped = self._apply_tounicode(raw_bytes, font_name)
            if mapped is not None:
                return mapped
            return inner
        if raw.startswith("<") and raw.endswith(">"):
            hex_str = raw[1:-1].replace(" ", "")
            if len(hex_str) % 2 != 0:
                hex_str += "0"
            try:
                raw_bytes = bytes.fromhex(hex_str)
                if len(raw_bytes) >= 2 and raw_bytes[0] == 0xFE and raw_bytes[1] == 0xFF:
                    return raw_bytes[2:].decode("utf-16-be", errors="replace")
                mapped = self._apply_tounicode(raw_bytes, font_name)
                if mapped is not None:
                    return mapped
                return raw_bytes.decode("latin-1", errors="replace")
            except ValueError:
                return ""
        return raw

    def _process_tj_array(self, stack: List[str], font_name: str) -> str:
        """Обработать массив TJ, объединяя текстовые фрагменты."""
        parts: List[str] = []
        for item in stack:
            if item in ("[", "]"):
                continue
            try:
                val = float(item)
                # Большое отрицательное смещение означает пробел между словами
                if val < -100:
                    parts.append(" ")
                continue
            except ValueError:
                pass
            text = self._decode_string(item, font_name)
            if text:
                parts.append(text)
        return "".join(parts)
