"""Тесты для CLI-интерфейса с использованием моков."""

import json
import os
import tempfile

import pytest
from unittest.mock import patch, MagicMock, call, mock_open

from src.cli import PdfCli, HELP_TEXT, MENU_TEXT
from src.parser_base import ParseError

from tests.conftest import build_simple_pdf, build_table_pdf


class TestCliInit:
    def test_default_init(self):
        cli = PdfCli()
        assert cli._data is None
        assert cli._document is None
        assert cli._strategy == "stream"

    def test_custom_io(self):
        mock_input = MagicMock(return_value="0")
        mock_print = MagicMock()
        cli = PdfCli(input_fn=mock_input, print_fn=mock_print)
        cli.run()
        mock_print.assert_called()


class TestCliMenu:
    def test_exit_command(self):
        outputs = []
        cli = PdfCli(
            input_fn=MagicMock(return_value="0"),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("Выход" in str(o) for o in outputs)

    def test_help_command(self):
        inputs = iter(["8", "0"])
        outputs = []
        cli = PdfCli(
            input_fn=lambda _: next(inputs),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("Справочная информация" in str(o) or HELP_TEXT in str(o) for o in outputs)

    def test_unknown_command(self):
        inputs = iter(["99", "0"])
        outputs = []
        cli = PdfCli(
            input_fn=lambda _: next(inputs),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("Неизвестная команда" in str(o) for o in outputs)

    def test_eof_handling(self):
        outputs = []
        cli = PdfCli(
            input_fn=MagicMock(side_effect=EOFError),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("Выход" in str(o) for o in outputs)


class TestCliLoadPdf:
    def test_load_pdf_file(self):
        pdf_data = build_simple_pdf()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_data)
            f.flush()
            path = f.name

        try:
            inputs = iter(["1", path, "0"])
            outputs = []
            cli = PdfCli(
                input_fn=lambda _: next(inputs),
                print_fn=lambda x: outputs.append(x),
            )
            cli.run()
            assert any("загружен" in str(o).lower() or "Файл загружен" in str(o) for o in outputs)
        finally:
            os.unlink(path)

    def test_load_nonexistent_file(self):
        inputs = iter(["1", "/nonexistent/path.pdf", "0"])
        outputs = []
        cli = PdfCli(
            input_fn=lambda _: next(inputs),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("не найден" in str(o) for o in outputs)

    def test_load_empty_path(self):
        inputs = iter(["1", "", "0"])
        outputs = []
        cli = PdfCli(
            input_fn=lambda _: next(inputs),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("пустым" in str(o) for o in outputs)


class TestCliExtractText:
    def test_extract_text_no_doc(self):
        inputs = iter(["3", "0"])
        outputs = []
        cli = PdfCli(
            input_fn=lambda _: next(inputs),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("загрузите" in str(o).lower() for o in outputs)

    def test_extract_text_with_doc(self):
        pdf_data = build_simple_pdf("Test Content")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_data)
            f.flush()
            path = f.name

        try:
            inputs = iter(["1", path, "3", "0"])
            outputs = []
            cli = PdfCli(
                input_fn=lambda _: next(inputs),
                print_fn=lambda x: outputs.append(x),
            )
            cli.run()
            assert any("Test Content" in str(o) for o in outputs)
        finally:
            os.unlink(path)


class TestCliExtractTables:
    def test_extract_tables_no_doc(self):
        inputs = iter(["4", "0"])
        outputs = []
        cli = PdfCli(
            input_fn=lambda _: next(inputs),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("загрузите" in str(o).lower() for o in outputs)


class TestCliCompareStrategies:
    def test_compare_no_doc(self):
        inputs = iter(["5", "0"])
        outputs = []
        cli = PdfCli(
            input_fn=lambda _: next(inputs),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("загрузите" in str(o).lower() for o in outputs)

    def test_compare_with_doc(self):
        pdf_data = build_simple_pdf()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_data)
            f.flush()
            path = f.name

        try:
            inputs = iter(["1", path, "5", "0"])
            outputs = []
            cli = PdfCli(
                input_fn=lambda _: next(inputs),
                print_fn=lambda x: outputs.append(x),
            )
            cli.run()
            assert any("Сравнение" in str(o) or "Рекомендация" in str(o) or "рекомендация" in str(o).lower() for o in outputs)
        finally:
            os.unlink(path)


class TestCliExportJson:
    def test_export_no_doc(self):
        inputs = iter(["6", "0"])
        outputs = []
        cli = PdfCli(
            input_fn=lambda _: next(inputs),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("загрузите" in str(o).lower() for o in outputs)

    def test_export_json(self):
        pdf_data = build_simple_pdf()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f_pdf:
            f_pdf.write(pdf_data)
            f_pdf.flush()
            pdf_path = f_pdf.name

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f_json:
            json_path = f_json.name

        try:
            inputs = iter(["1", pdf_path, "6", json_path, "0"])
            outputs = []
            cli = PdfCli(
                input_fn=lambda _: next(inputs),
                print_fn=lambda x: outputs.append(x),
            )
            cli.run()

            assert os.path.exists(json_path)
            with open(json_path, "r") as f:
                data = json.load(f)
            assert "document" in data
        finally:
            os.unlink(pdf_path)
            if os.path.exists(json_path):
                os.unlink(json_path)


class TestCliManualInput:
    def test_set_strategy(self):
        inputs = iter(["7", "xref", "0"])
        outputs = []
        cli = PdfCli(
            input_fn=lambda _: next(inputs),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("xref" in str(o) for o in outputs)

    def test_invalid_strategy(self):
        inputs = iter(["7", "bogus", "0"])
        outputs = []
        cli = PdfCli(
            input_fn=lambda _: next(inputs),
            print_fn=lambda x: outputs.append(x),
        )
        cli.run()
        assert any("Неизвестная стратегия" in str(o) for o in outputs)


class TestCliJsonConfig:
    def test_load_json_config(self):
        pdf_data = build_simple_pdf()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f_pdf:
            f_pdf.write(pdf_data)
            f_pdf.flush()
            pdf_path = f_pdf.name

        config = {
            "input_file": pdf_path,
            "strategy": "stream",
        }

        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f_cfg:
            json.dump(config, f_cfg)
            f_cfg.flush()
            cfg_path = f_cfg.name

        try:
            inputs = iter(["2", cfg_path, "0"])
            outputs = []
            cli = PdfCli(
                input_fn=lambda _: next(inputs),
                print_fn=lambda x: outputs.append(x),
            )
            cli.run()
            assert any("Загружен" in str(o) or "загружен" in str(o) for o in outputs)
        finally:
            os.unlink(pdf_path)
            os.unlink(cfg_path)

    def test_load_invalid_json(self):
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            f.write("not valid json{{{")
            f.flush()
            path = f.name

        try:
            inputs = iter(["2", path, "0"])
            outputs = []
            cli = PdfCli(
                input_fn=lambda _: next(inputs),
                print_fn=lambda x: outputs.append(x),
            )
            cli.run()
            assert any("Ошибка" in str(o) for o in outputs)
        finally:
            os.unlink(path)
