"""Базовый интерфейс для PDF-парсеров."""

from __future__ import annotations

import zlib
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from .pdf_objects import (
    PdfArray,
    PdfDict,
    PdfInteger,
    PdfName,
    PdfObject,
    PdfReference,
    PdfStream,
)


class ParseError(Exception):
    """Ошибка парсинга PDF."""


class PdfParserBase(ABC):
    """Абстрактный базовый класс для стратегий парсинга PDF."""

    @abstractmethod
    def parse(self, data: bytes) -> Dict[int, Any]:
        """Разобрать PDF и вернуть словарь номер_объекта -> объект."""

    @abstractmethod
    def get_version(self, data: bytes) -> str:
        """Извлечь версию PDF из заголовка."""

    @abstractmethod
    def get_root_ref(self, data: bytes) -> Optional[PdfReference]:
        """Получить ссылку на корневой объект (каталог)."""

    def resolve(
        self, obj: PdfObject, objects: Dict[int, Any], depth: int = 0
    ) -> PdfObject:
        """Разрешить косвенную ссылку до реального объекта."""
        if depth > 50:
            return obj
        if isinstance(obj, PdfReference):
            resolved = objects.get(obj.obj_num)
            if resolved is not None:
                return self.resolve(resolved, objects, depth + 1)
            return obj
        return obj

    def decode_stream(self, stream: PdfStream) -> bytes:
        """Декодировать данные потока с применением фильтров."""
        data = stream.raw_data
        filter_obj = stream.get("Filter")

        if filter_obj is None:
            return data

        filters = []
        if isinstance(filter_obj, PdfName):
            filters = [filter_obj.name]
        elif hasattr(filter_obj, "items"):
            filters = [
                f.name if isinstance(f, PdfName) else str(f) for f in filter_obj.items
            ]

        for f in filters:
            if f == "FlateDecode":
                try:
                    data = zlib.decompress(data)
                except zlib.error:
                    try:
                        data = zlib.decompress(data, -15)
                    except zlib.error:
                        pass
            elif f == "ASCIIHexDecode":
                data = self._decode_ascii_hex(data)
            elif f == "ASCII85Decode":
                data = self._decode_ascii85(data)

        return data

    @staticmethod
    def _decode_ascii_hex(data: bytes) -> bytes:
        text = data.decode("ascii", errors="ignore").replace(" ", "").replace("\n", "")
        if text.endswith(">"):
            text = text[:-1]
        if len(text) % 2 != 0:
            text += "0"
        return bytes.fromhex(text)

    @staticmethod
    def _decode_ascii85(data: bytes) -> bytes:
        text = data.decode("ascii", errors="ignore").strip()
        if text.startswith("<~"):
            text = text[2:]
        if text.endswith("~>"):
            text = text[:-2]

        result = bytearray()
        i = 0
        while i < len(text):
            if text[i] == "z":
                result.extend(b"\x00\x00\x00\x00")
                i += 1
                continue

            chunk = text[i : i + 5]
            i += len(chunk)

            padding = 5 - len(chunk)
            chunk += "u" * padding

            acc = 0
            for c in chunk:
                acc = acc * 85 + (ord(c) - 33)

            decoded = acc.to_bytes(4, "big")
            result.extend(decoded[: 4 - padding])

        return bytes(result)

    def extract_objects_from_objstm(
        self, stream: PdfStream
    ) -> Dict[int, Any]:
        """Извлечь объекты из потока объектов (ObjStm, PDF 1.5+).

        В PDF 1.5+ несколько объектов могут быть сжаты в одном потоке.
        Заголовок потока содержит пары (номер_объекта, смещение),
        за которыми следуют данные объектов начиная со смещения First.
        """
        from .tokenizer import PdfTokenizer, TokenizerError

        n_obj = stream.get("N")
        first_obj = stream.get("First")
        if not isinstance(n_obj, PdfInteger) or not isinstance(first_obj, PdfInteger):
            return {}

        n = n_obj.value
        first = first_obj.value
        decoded = self.decode_stream(stream)
        if not decoded:
            return {}

        header_tok = PdfTokenizer(decoded)
        pairs: List[Tuple[int, int]] = []
        try:
            for _ in range(n):
                header_tok.skip_whitespace()
                obj_num_token = header_tok.read_number()
                header_tok.skip_whitespace()
                offset_token = header_tok.read_number()
                if isinstance(obj_num_token, PdfInteger) and isinstance(
                    offset_token, PdfInteger
                ):
                    pairs.append((obj_num_token.value, offset_token.value))
        except TokenizerError:
            pass

        result: Dict[int, Any] = {}
        for i, (obj_num, offset) in enumerate(pairs):
            abs_offset = first + offset
            tok = PdfTokenizer(decoded)
            tok.pos = abs_offset
            try:
                obj = tok.read_object()
                result[obj_num] = obj
            except TokenizerError:
                continue

        return result

    def parse_xref_stream(
        self, stream: PdfStream
    ) -> Tuple[Dict[int, Any], Dict[int, int]]:
        """Разобрать поток перекрёстных ссылок (XRef stream, PDF 1.5+).

        Возвращает кортеж:
          - словарь с данными трейлера (Root, Info и т.д.);
            в ключе '_compressed' — список сжатых объектов (тип 2);
          - словарь номер_объекта -> смещение в файле (тип 1).
        """
        decoded = self.decode_stream(stream)
        d = stream.dictionary

        w_arr = d.get("W")
        if not isinstance(w_arr, PdfArray) or len(w_arr) < 3:
            return {}, {}
        w = [
            e.value if isinstance(e, PdfInteger) else 0
            for e in w_arr
        ]

        idx_arr = d.get("Index")
        if isinstance(idx_arr, PdfArray) and len(idx_arr) >= 2:
            index_pairs = []
            items = idx_arr.items if hasattr(idx_arr, "items") else list(idx_arr)
            for j in range(0, len(items), 2):
                start_val = items[j]
                count_val = items[j + 1] if j + 1 < len(items) else PdfInteger(0)
                s = start_val.value if isinstance(start_val, PdfInteger) else 0
                c = count_val.value if isinstance(count_val, PdfInteger) else 0
                index_pairs.append((s, c))
        else:
            size_obj = d.get("Size")
            total = size_obj.value if isinstance(size_obj, PdfInteger) else 0
            index_pairs = [(0, total)]

        entry_size = sum(w)
        pos = 0
        offsets: Dict[int, int] = {}
        compressed: List[Tuple[int, int, int]] = []

        for start_obj, count in index_pairs:
            for i in range(count):
                if pos + entry_size > len(decoded):
                    break
                entry = decoded[pos: pos + entry_size]
                f1 = int.from_bytes(entry[0: w[0]], "big") if w[0] else 1
                f2 = int.from_bytes(entry[w[0]: w[0] + w[1]], "big") if w[1] else 0
                f3 = int.from_bytes(
                    entry[w[0] + w[1]: w[0] + w[1] + w[2]], "big"
                ) if w[2] else 0
                obj_num = start_obj + i
                if f1 == 1 and f2 > 0:
                    offsets[obj_num] = f2
                elif f1 == 2:
                    compressed.append((obj_num, f2, f3))
                pos += entry_size

        xref_info: Dict[str, Any] = {}
        for key in ("Root", "Info", "ID", "Size", "Prev"):
            val = d.get(key)
            if val is not None:
                xref_info[key] = val
        xref_info["_compressed"] = compressed

        return xref_info, offsets

    def validate_header(self, data: bytes) -> bool:
        """Проверить, начинаются ли данные с корректного заголовка PDF."""
        if len(data) < 8:
            return False
        return data[:5] == b"%PDF-"

    def extract_version(self, data: bytes) -> str:
        """Извлечь строку версии из заголовка PDF."""
        if not self.validate_header(data):
            raise ParseError("Invalid PDF header")
        end = data.find(b"\n", 0, 20)
        if end == -1:
            end = data.find(b"\r", 0, 20)
        if end == -1:
            end = min(12, len(data))
        header = data[:end].decode("latin-1").strip()
        version = header[5:]
        return version
