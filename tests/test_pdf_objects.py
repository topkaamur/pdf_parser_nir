"""Тесты для типов PDF-объектов."""

import pytest
from hamcrest import assert_that, equal_to, has_length, contains_string

from src.pdf_objects import (
    PdfArray,
    PdfBoolean,
    PdfDict,
    PdfHexString,
    PdfInteger,
    PdfName,
    PdfNull,
    PdfReal,
    PdfReference,
    PdfStream,
    PdfString,
)


class TestPdfString:
    def test_ascii_text(self):
        s = PdfString(b"Hello")
        assert s.text == "Hello"

    def test_utf16be_text(self):
        raw = b"\xfe\xff" + "Привет".encode("utf-16-be")
        s = PdfString(raw)
        assert s.text == "Привет"

    def test_latin1_text(self):
        s = PdfString(b"\xe9")
        assert s.text == "é"

    def test_empty_string(self):
        s = PdfString(b"")
        assert s.text == ""


class TestPdfHexString:
    def test_ascii_hex(self):
        h = PdfHexString(b"Hello")
        assert h.text == "Hello"

    def test_utf16be_hex(self):
        raw = b"\xfe\xff" + "Тест".encode("utf-16-be")
        h = PdfHexString(raw)
        assert h.text == "Тест"


class TestPdfName:
    def test_equality(self):
        n1 = PdfName("Type")
        n2 = PdfName("Type")
        assert n1 == n2

    def test_equality_with_string(self):
        n = PdfName("Type")
        assert n == "Type"

    def test_hash(self):
        n1 = PdfName("Type")
        n2 = PdfName("Type")
        assert hash(n1) == hash(n2)

    def test_inequality(self):
        n1 = PdfName("Type")
        n2 = PdfName("Page")
        assert n1 != n2


class TestPdfArray:
    def test_len(self):
        a = PdfArray([PdfInteger(1), PdfInteger(2)])
        assert_that(a, has_length(2))

    def test_getitem(self):
        a = PdfArray([PdfInteger(10), PdfInteger(20)])
        assert a[0].value == 10
        assert a[1].value == 20

    def test_iter(self):
        items = [PdfInteger(1), PdfInteger(2), PdfInteger(3)]
        a = PdfArray(items)
        result = list(a)
        assert len(result) == 3

    def test_empty(self):
        a = PdfArray()
        assert len(a) == 0


class TestPdfDict:
    def test_get(self):
        d = PdfDict({"Type": PdfName("Catalog")})
        assert d.get("Type") == PdfName("Catalog")

    def test_get_missing(self):
        d = PdfDict({})
        assert d.get("Missing") is None
        assert d.get("Missing", "default") == "default"

    def test_contains(self):
        d = PdfDict({"Type": PdfName("Catalog")})
        assert "Type" in d
        assert "Missing" not in d

    def test_len(self):
        d = PdfDict({"A": PdfInteger(1), "B": PdfInteger(2)})
        assert len(d) == 2

    def test_keys(self):
        d = PdfDict({"A": PdfInteger(1), "B": PdfInteger(2)})
        assert set(d.keys()) == {"A", "B"}

    def test_getitem(self):
        d = PdfDict({"X": PdfInteger(42)})
        assert d["X"].value == 42

    def test_getitem_missing_raises(self):
        d = PdfDict({})
        with pytest.raises(KeyError):
            _ = d["missing"]


class TestPdfStream:
    def test_get(self):
        d = PdfDict({"Length": PdfInteger(5)})
        s = PdfStream(d, b"Hello")
        assert s.get("Length").value == 5

    def test_contains(self):
        d = PdfDict({"Type": PdfName("XObject")})
        s = PdfStream(d)
        assert "Type" in s
        assert "Missing" not in s


class TestPdfReference:
    def test_repr(self):
        r = PdfReference(1, 0)
        assert_that(str(r), equal_to("1 0 R"))

    def test_equality(self):
        r1 = PdfReference(1, 0)
        r2 = PdfReference(1, 0)
        assert r1 == r2

    def test_inequality(self):
        r1 = PdfReference(1, 0)
        r2 = PdfReference(2, 0)
        assert r1 != r2

    def test_hash(self):
        r1 = PdfReference(5, 0)
        r2 = PdfReference(5, 0)
        assert hash(r1) == hash(r2)
        s = {r1}
        assert r2 in s

    def test_inequality_with_other_type(self):
        r = PdfReference(1, 0)
        assert r != "1 0 R"


class TestPdfNull:
    def test_repr(self):
        n = PdfNull()
        assert repr(n) == "null"


class TestPdfBoolean:
    def test_true(self):
        b = PdfBoolean(True)
        assert b.value is True

    def test_false(self):
        b = PdfBoolean(False)
        assert b.value is False
