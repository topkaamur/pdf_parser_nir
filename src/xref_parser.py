"""Стратегия 2: Парсер PDF на основе таблицы перекрёстных ссылок (XRef).

Читает таблицу xref для построения индекса позиций объектов,
затем читает объекты по смещению. Эффективнее для больших файлов
благодаря произвольному доступу.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .parser_base import ParseError, PdfParserBase
from .pdf_objects import PdfDict, PdfInteger, PdfName, PdfReference, PdfStream
from .tokenizer import PdfTokenizer, TokenizerError


class XRefPdfParser(PdfParserBase):
    """Парсит PDF с использованием таблицы xref для индексированного доступа."""

    def get_version(self, data: bytes) -> str:
        return self.extract_version(data)

    def get_root_ref(self, data: bytes) -> Optional[PdfReference]:
        """Получить ссылку на Root из словаря trailer или XRef-потока."""
        trailer = self._read_trailer(data)
        if trailer is not None:
            root = trailer.get("Root")
            if isinstance(root, PdfReference):
                return root

        return self._get_root_from_xref_stream(data)

    def _get_root_from_xref_stream(self, data: bytes) -> Optional[PdfReference]:
        """Извлечь Root из объекта-потока перекрёстных ссылок."""
        try:
            startxref = self._find_startxref(data)
        except ParseError:
            return None

        obj = self._read_object_at(data, startxref)
        if isinstance(obj, PdfStream):
            type_val = obj.get("Type")
            if isinstance(type_val, PdfName) and type_val.name == "XRef":
                root = obj.dictionary.get("Root")
                if isinstance(root, PdfReference):
                    return root
        return None

    def _find_startxref(self, data: bytes) -> int:
        """Найти значение startxref в конце файла."""
        search_region = data[-1024:] if len(data) > 1024 else data

        marker = search_region.rfind(b"startxref")
        if marker == -1:
            raise ParseError("Cannot find startxref marker")

        after_marker = search_region[marker + 9 :]
        num_str = after_marker.strip().split(b"\n")[0].split(b"\r")[0].strip()
        try:
            return int(num_str)
        except ValueError:
            raise ParseError(f"Invalid startxref value: {num_str!r}")

    def _read_xref_table(self, data: bytes, offset: int) -> Dict[int, int]:
        """Прочитать таблицу xref и вернуть словарь номер_объекта -> смещение."""
        xref_offsets: Dict[int, int] = {}

        if offset >= len(data):
            raise ParseError(f"Xref offset {offset} is beyond file end")

        if data[offset : offset + 4] != b"xref":
            raise ParseError(f"Expected 'xref' at offset {offset}")

        pos = offset + 4
        while pos < len(data):
            line_end = data.find(b"\n", pos)
            if line_end == -1:
                line_end = len(data)
            line = data[pos:line_end].strip()
            pos = line_end + 1

            if not line:
                continue
            if line.startswith(b"trailer"):
                break

            parts = line.split()
            if len(parts) == 2 and parts[0].isdigit():
                start_obj = int(parts[0])
                count = int(parts[1])
                for i in range(count):
                    if pos >= len(data):
                        break
                    entry_end = data.find(b"\n", pos)
                    if entry_end == -1:
                        entry_end = len(data)
                    entry = data[pos:entry_end].strip()
                    pos = entry_end + 1

                    entry_parts = entry.split()
                    if len(entry_parts) >= 3:
                        file_offset = int(entry_parts[0])
                        status = entry_parts[2]
                        if status == b"n" and file_offset > 0:
                            xref_offsets[start_obj + i] = file_offset

        return xref_offsets

    def _read_trailer(self, data: bytes) -> Optional[PdfDict]:
        """Прочитать словарь trailer."""
        trailer_pos = data.rfind(b"trailer")
        if trailer_pos == -1:
            return None

        tokenizer = PdfTokenizer(data)
        tokenizer.pos = trailer_pos + 7
        try:
            tokenizer.skip_whitespace()
            return tokenizer.read_dictionary()
        except TokenizerError:
            return None

    def _read_trailer_or_xref_stream(self, data: bytes) -> Optional[PdfDict]:
        """Прочитать trailer из ключевого слова 'trailer' или XRef-потока."""
        trailer = self._read_trailer(data)
        if trailer is not None:
            return trailer

        try:
            startxref = self._find_startxref(data)
        except ParseError:
            return None

        obj = self._read_object_at(data, startxref)
        if isinstance(obj, PdfStream):
            type_val = obj.get("Type")
            if isinstance(type_val, PdfName) and type_val.name == "XRef":
                entries: Dict[str, Any] = {}
                for key in ("Root", "Info", "ID", "Size", "Prev"):
                    val = obj.dictionary.get(key)
                    if val is not None:
                        entries[key] = val
                return PdfDict(entries)
        return None

    def _read_object_at(self, data: bytes, offset: int) -> Any:
        """Прочитать один объект по указанному смещению в файле."""
        tokenizer = PdfTokenizer(data)
        tokenizer.pos = offset

        try:
            obj_num = tokenizer.read_object()
            gen_num = tokenizer.read_object()

            tokenizer.skip_whitespace()
            keyword = tokenizer.read_keyword()
            if keyword != "obj":
                return None

            tokenizer.skip_whitespace()
            obj = tokenizer.read_object()

            if isinstance(obj, PdfDict):
                stream_data = tokenizer.read_stream_data(obj)
                if stream_data:
                    obj = PdfStream(obj, stream_data)

            return obj
        except TokenizerError:
            return None

    def parse(self, data: bytes) -> Dict[int, Any]:
        """Разобрать все объекты через таблицу xref."""
        if not self.validate_header(data):
            raise ParseError("Invalid PDF: missing header")

        try:
            startxref = self._find_startxref(data)
        except ParseError:
            raise

        objects: Dict[int, Any] = {}

        is_xref_stream = (
            startxref < len(data)
            and data[startxref: startxref + 4] != b"xref"
        )

        if is_xref_stream:
            xref_stream_obj = self._read_object_at(data, startxref)
        else:
            xref_stream_obj = None

        if (
            isinstance(xref_stream_obj, PdfStream)
            and xref_stream_obj.get("Type") == "XRef"
        ):
            xref_info, offsets = self.parse_xref_stream(xref_stream_obj)

            for obj_num, offset in offsets.items():
                obj = self._read_object_at(data, offset)
                if obj is not None:
                    objects[obj_num] = obj

            compressed = xref_info.get("_compressed", [])
            objstm_nums = set()
            for obj_num, stream_num, idx in compressed:
                objstm_nums.add(stream_num)

            for sn in objstm_nums:
                if sn in objects and isinstance(objects[sn], PdfStream):
                    extracted = self.extract_objects_from_objstm(objects[sn])
                    for on, ov in extracted.items():
                        if on not in objects:
                            objects[on] = ov
        else:
            try:
                xref_table = self._read_xref_table(data, startxref)
            except ParseError:
                raise

            for obj_num, offset in xref_table.items():
                obj = self._read_object_at(data, offset)
                if obj is not None:
                    objects[obj_num] = obj

            self._expand_object_streams(objects)

        return objects

    def _expand_object_streams(self, objects: Dict[int, Any]) -> None:
        """Распаковать объекты из ObjStm-потоков и добавить в словарь."""
        objstm_keys = [
            k for k, v in objects.items()
            if isinstance(v, PdfStream) and v.get("Type") == "ObjStm"
        ]
        for k in objstm_keys:
            extracted = self.extract_objects_from_objstm(objects[k])
            for obj_num, obj in extracted.items():
                if obj_num not in objects:
                    objects[obj_num] = obj

    def get_metadata(self, data: bytes) -> Dict[str, str]:
        """Извлечь метаданные документа из словаря Info."""
        trailer = self._read_trailer_or_xref_stream(data)
        if trailer is None:
            return {}

        info_ref = trailer.get("Info")
        if not isinstance(info_ref, PdfReference):
            return {}

        objects = self.parse(data)
        info = self.resolve(info_ref, objects)
        if not isinstance(info, PdfDict):
            return {}

        metadata = {}
        for key in ("Title", "Author", "Subject", "Creator", "Producer"):
            val = info.get(key)
            if val is not None:
                if hasattr(val, "text"):
                    metadata[key] = val.text
                elif hasattr(val, "value"):
                    metadata[key] = str(val.value)

        return metadata
