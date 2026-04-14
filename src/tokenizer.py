"""Токенизатор PDF — разбивает байтовый поток PDF на токены."""

from __future__ import annotations

from typing import Optional, Tuple, Union

from .pdf_objects import (
    PdfArray,
    PdfBoolean,
    PdfDict,
    PdfHexString,
    PdfInteger,
    PdfName,
    PdfNull,
    PdfObject,
    PdfReal,
    PdfReference,
    PdfStream,
    PdfString,
)

PDF_WHITESPACE = b" \t\n\r\x00\x0c"
PDF_DELIMITERS = b"()<>[]{}/%"


class TokenizerError(Exception):
    """Ошибка токенизации."""


class PdfTokenizer:
    """Разбирает байтовый поток PDF в объекты PDF."""

    def __init__(self, data: bytes):
        if not isinstance(data, bytes):
            raise TokenizerError("Input must be bytes")
        self.data = data
        self.pos = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    @property
    def at_end(self) -> bool:
        return self.pos >= len(self.data)

    def peek(self, offset: int = 0) -> Optional[int]:
        idx = self.pos + offset
        if idx < len(self.data):
            return self.data[idx]
        return None

    def read_byte(self) -> int:
        if self.pos >= len(self.data):
            raise TokenizerError("Unexpected end of data")
        b = self.data[self.pos]
        self.pos += 1
        return b

    def skip_whitespace(self) -> None:
        while self.pos < len(self.data):
            b = self.data[self.pos]
            if bytes([b]) in [bytes([w]) for w in PDF_WHITESPACE]:
                self.pos += 1
            elif b == ord("%"):
                self._skip_comment()
            else:
                break

    def _skip_comment(self) -> None:
        while self.pos < len(self.data) and self.data[self.pos] not in (
            ord("\n"),
            ord("\r"),
        ):
            self.pos += 1
        if self.pos < len(self.data):
            self.pos += 1

    def read_number(self) -> Union[PdfInteger, PdfReal]:
        """Прочитать числовой токен (целое или вещественное)."""
        start = self.pos
        if self.pos < len(self.data) and self.data[self.pos] in (
            ord("+"),
            ord("-"),
        ):
            self.pos += 1

        has_dot = False
        while self.pos < len(self.data):
            ch = self.data[self.pos]
            if ch == ord("."):
                if has_dot:
                    break
                has_dot = True
                self.pos += 1
            elif ord("0") <= ch <= ord("9"):
                self.pos += 1
            else:
                break

        token = self.data[start : self.pos]
        if not token or token in (b"+", b"-", b"."):
            raise TokenizerError(f"Invalid number at position {start}")

        if has_dot:
            return PdfReal(float(token))
        return PdfInteger(int(token))

    def read_literal_string(self) -> PdfString:
        """Прочитать строку в круглых скобках."""
        if self.data[self.pos] != ord("("):
            raise TokenizerError(f"Expected '(' at position {self.pos}")
        self.pos += 1

        result = bytearray()
        depth = 1

        while self.pos < len(self.data) and depth > 0:
            ch = self.data[self.pos]
            if ch == ord("\\"):
                self.pos += 1
                if self.pos >= len(self.data):
                    break
                esc = self.data[self.pos]
                if esc == ord("n"):
                    result.append(ord("\n"))
                elif esc == ord("r"):
                    result.append(ord("\r"))
                elif esc == ord("t"):
                    result.append(ord("\t"))
                elif esc == ord("b"):
                    result.append(ord("\b"))
                elif esc == ord("f"):
                    result.append(ord("\f"))
                elif esc == ord("("):
                    result.append(ord("("))
                elif esc == ord(")"):
                    result.append(ord(")"))
                elif esc == ord("\\"):
                    result.append(ord("\\"))
                elif ord("0") <= esc <= ord("7"):
                    octal = chr(esc)
                    for _ in range(2):
                        if (
                            self.pos + 1 < len(self.data)
                            and ord("0") <= self.data[self.pos + 1] <= ord("7")
                        ):
                            self.pos += 1
                            octal += chr(self.data[self.pos])
                        else:
                            break
                    result.append(int(octal, 8) & 0xFF)
                elif esc in (ord("\n"), ord("\r")):
                    if (
                        esc == ord("\r")
                        and self.pos + 1 < len(self.data)
                        and self.data[self.pos + 1] == ord("\n")
                    ):
                        self.pos += 1
                else:
                    result.append(esc)
            elif ch == ord("("):
                depth += 1
                result.append(ch)
            elif ch == ord(")"):
                depth -= 1
                if depth > 0:
                    result.append(ch)
            else:
                result.append(ch)
            self.pos += 1

        if depth != 0:
            raise TokenizerError("Unterminated string literal")

        return PdfString(bytes(result))

    def read_hex_string(self) -> PdfHexString:
        """Прочитать шестнадцатеричную строку в угловых скобках."""
        if self.data[self.pos] != ord("<"):
            raise TokenizerError(f"Expected '<' at position {self.pos}")
        self.pos += 1

        hex_chars = bytearray()
        while self.pos < len(self.data) and self.data[self.pos] != ord(">"):
            ch = self.data[self.pos]
            if bytes([ch]) not in [bytes([w]) for w in PDF_WHITESPACE]:
                if not (
                    (ord("0") <= ch <= ord("9"))
                    or (ord("a") <= ch <= ord("f"))
                    or (ord("A") <= ch <= ord("F"))
                ):
                    raise TokenizerError(
                        f"Invalid hex character {chr(ch)} at position {self.pos}"
                    )
                hex_chars.append(ch)
            self.pos += 1

        if self.pos >= len(self.data):
            raise TokenizerError("Unterminated hex string")
        self.pos += 1

        hex_str = hex_chars.decode("ascii")
        if len(hex_str) % 2 != 0:
            hex_str += "0"

        return PdfHexString(bytes.fromhex(hex_str))

    def read_name(self) -> PdfName:
        """Прочитать именованный объект, начинающийся с /."""
        if self.data[self.pos] != ord("/"):
            raise TokenizerError(f"Expected '/' at position {self.pos}")
        self.pos += 1

        name_bytes = bytearray()
        while self.pos < len(self.data):
            ch = self.data[self.pos]
            if (
                bytes([ch]) in [bytes([w]) for w in PDF_WHITESPACE]
                or ch in PDF_DELIMITERS
            ):
                break
            if ch == ord("#") and self.pos + 2 < len(self.data):
                hex_val = self.data[self.pos + 1 : self.pos + 3]
                try:
                    name_bytes.append(int(hex_val, 16))
                    self.pos += 3
                    continue
                except ValueError:
                    pass
            name_bytes.append(ch)
            self.pos += 1

        return PdfName(name_bytes.decode("latin-1"))

    def read_keyword(self) -> str:
        """Прочитать ключевое слово."""
        start = self.pos
        while self.pos < len(self.data):
            ch = self.data[self.pos]
            if (
                bytes([ch]) in [bytes([w]) for w in PDF_WHITESPACE]
                or ch in PDF_DELIMITERS
            ):
                break
            self.pos += 1
        return self.data[start : self.pos].decode("latin-1")

    def read_object(self) -> PdfObject:
        """Прочитать следующий PDF-объект из потока."""
        self.skip_whitespace()
        if self.at_end:
            raise TokenizerError("Unexpected end of data while reading object")

        ch = self.data[self.pos]

        if ch == ord("("):
            return self.read_literal_string()

        if ch == ord("<"):
            if self.pos + 1 < len(self.data) and self.data[self.pos + 1] == ord("<"):
                return self.read_dictionary()
            return self.read_hex_string()

        if ch == ord("/"):
            return self.read_name()

        if ch == ord("["):
            return self.read_array()

        if ord("0") <= ch <= ord("9") or ch in (ord("+"), ord("-"), ord(".")):
            return self._read_number_or_reference()

        keyword = self.read_keyword()
        if keyword == "true":
            return PdfBoolean(True)
        if keyword == "false":
            return PdfBoolean(False)
        if keyword == "null":
            return PdfNull()
        raise TokenizerError(f"Unexpected keyword '{keyword}' at position {self.pos}")

    def _read_number_or_reference(self) -> Union[PdfInteger, PdfReal, PdfReference]:
        """Прочитать число или косвенную ссылку (N M R)."""
        saved_pos = self.pos
        num = self.read_number()

        if not isinstance(num, PdfInteger) or num.value < 0:
            return num

        saved_pos2 = self.pos
        self.skip_whitespace()

        if self.at_end:
            self.pos = saved_pos2
            return num

        ch = self.data[self.pos] if not self.at_end else None
        if ch is not None and (ord("0") <= ch <= ord("9")):
            gen = self.read_number()
            if isinstance(gen, PdfInteger) and gen.value >= 0:
                self.skip_whitespace()
                if not self.at_end and self.data[self.pos] == ord("R"):
                    self.pos += 1
                    return PdfReference(num.value, gen.value)
            self.pos = saved_pos2
            return num

        self.pos = saved_pos2
        return num

    def read_array(self) -> PdfArray:
        """Прочитать массив PDF [...]."""
        if self.data[self.pos] != ord("["):
            raise TokenizerError(f"Expected '[' at position {self.pos}")
        self.pos += 1

        items = []
        while True:
            self.skip_whitespace()
            if self.at_end:
                raise TokenizerError("Unterminated array")
            if self.data[self.pos] == ord("]"):
                self.pos += 1
                break
            items.append(self.read_object())

        return PdfArray(items)

    def read_dictionary(self) -> PdfDict:
        """Прочитать словарь PDF << ... >>."""
        if (
            self.pos + 1 >= len(self.data)
            or self.data[self.pos] != ord("<")
            or self.data[self.pos + 1] != ord("<")
        ):
            raise TokenizerError(f"Expected '<<' at position {self.pos}")
        self.pos += 2

        entries = {}
        while True:
            self.skip_whitespace()
            if self.at_end:
                raise TokenizerError("Unterminated dictionary")
            if (
                self.data[self.pos] == ord(">")
                and self.pos + 1 < len(self.data)
                and self.data[self.pos + 1] == ord(">")
            ):
                self.pos += 2
                break

            key = self.read_name()
            self.skip_whitespace()
            value = self.read_object()
            entries[key.name] = value

        return PdfDict(entries)

    def read_stream_data(self, dictionary: PdfDict) -> bytes:
        """Прочитать данные потока, следующие за словарём."""
        self.skip_whitespace()
        if self.pos + 6 > len(self.data):
            return b""

        marker = self.data[self.pos : self.pos + 6]
        if marker != b"stream":
            return b""
        self.pos += 6

        if self.pos < len(self.data) and self.data[self.pos] == ord("\r"):
            self.pos += 1
        if self.pos < len(self.data) and self.data[self.pos] == ord("\n"):
            self.pos += 1

        length_obj = dictionary.get("Length")
        if isinstance(length_obj, PdfInteger):
            length = length_obj.value
            if length < 0:
                length = 0
            end_pos = min(self.pos + length, len(self.data))
            data = self.data[self.pos : end_pos]
            self.pos = end_pos
        else:
            end_marker = self.data.find(b"endstream", self.pos)
            if end_marker == -1:
                data = self.data[self.pos :]
                self.pos = len(self.data)
            else:
                data = self.data[self.pos : end_marker]
                self.pos = end_marker

        end_marker_pos = self.data.find(b"endstream", self.pos)
        if end_marker_pos != -1 and end_marker_pos - self.pos < 10:
            self.pos = end_marker_pos + 9

        if data.endswith(b"\r\n"):
            data = data[:-2]
        elif data.endswith(b"\n") or data.endswith(b"\r"):
            data = data[:-1]

        return data
