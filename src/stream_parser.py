"""Стратегия 1: Потоковый (последовательный) парсер PDF.

Последовательно сканирует файл, находя объекты по паттерну
'N M obj ... endobj'. Не зависит от таблицы xref, что делает
его устойчивым к повреждённым файлам.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .parser_base import ParseError, PdfParserBase
from .pdf_objects import PdfDict, PdfName, PdfReference, PdfStream
from .tokenizer import PdfTokenizer, TokenizerError


class StreamPdfParser(PdfParserBase):
    """Парсит PDF последовательным сканированием байтового потока."""

    def get_version(self, data: bytes) -> str:
        return self.extract_version(data)

    def get_root_ref(self, data: bytes) -> Optional[PdfReference]:
        """Найти ссылку на Root, начиная с поиска словаря trailer."""
        trailer_pos = data.rfind(b"trailer")
        if trailer_pos != -1:
            tokenizer = PdfTokenizer(data)
            tokenizer.pos = trailer_pos + 7
            try:
                tokenizer.skip_whitespace()
                trailer_dict = tokenizer.read_dictionary()
                root = trailer_dict.get("Root")
                if isinstance(root, PdfReference):
                    return root
            except TokenizerError:
                pass

        return self._find_root_in_objects(data)

    def _find_root_in_objects(self, data: bytes) -> Optional[PdfReference]:
        """Запасной вариант: поиск каталога среди объектов, включая XRef-потоки."""
        objects = self._parse_raw_objects(data)

        for obj_num, obj in objects.items():
            if isinstance(obj, PdfStream) and obj.get("Type") == "XRef":
                root = obj.dictionary.get("Root")
                if isinstance(root, PdfReference):
                    return root

        all_objects = dict(objects)
        self._expand_object_streams(all_objects)

        for obj_num, obj in all_objects.items():
            if isinstance(obj, PdfDict) and obj.get("Type") == "Catalog":
                return PdfReference(obj_num, 0)
            if isinstance(obj, PdfStream) and obj.get("Type") == "Catalog":
                return PdfReference(obj_num, 0)
        return None

    def _parse_raw_objects(self, data: bytes) -> Dict[int, Any]:
        """Разобрать объекты верхнего уровня (без распаковки ObjStm)."""
        if not self.validate_header(data):
            raise ParseError("Invalid PDF: missing header")

        objects: Dict[int, Any] = {}
        obj_pattern = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")

        for match in obj_pattern.finditer(data):
            obj_num = int(match.group(1))
            start = match.end()

            tokenizer = PdfTokenizer(data)
            tokenizer.pos = start

            try:
                tokenizer.skip_whitespace()
                obj = tokenizer.read_object()

                if isinstance(obj, PdfDict):
                    stream_data = tokenizer.read_stream_data(obj)
                    if stream_data:
                        obj = PdfStream(obj, stream_data)

                objects[obj_num] = obj
            except TokenizerError:
                continue

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

    def parse(self, data: bytes) -> Dict[int, Any]:
        """Разобрать все объекты последовательным сканированием файла."""
        objects = self._parse_raw_objects(data)
        self._expand_object_streams(objects)
        return objects
