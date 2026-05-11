from __future__ import annotations

import io
from types import SimpleNamespace

import pytest


class _FakeStreamlit:
    def __init__(self) -> None:
        self.downloads: list[dict[str, object]] = []
        self.warnings: list[str] = []
        self.images: list[tuple[object, str | None]] = []
        self.markdowns: list[tuple[str, bool]] = []
        self.infos: list[str] = []

    def download_button(self, label, data=None, file_name=None, mime=None):
        self.downloads.append(
            {"label": label, "data": data, "file_name": file_name, "mime": mime}
        )

    def warning(self, message):
        self.warnings.append(str(message))

    def image(self, data, caption=None):
        self.images.append((data, caption))

    def markdown(self, text, unsafe_allow_html=False):
        self.markdowns.append((str(text), bool(unsafe_allow_html)))

    def info(self, message):
        self.infos.append(str(message))


@pytest.fixture
def ui_utils_module(monkeypatch, tmp_path):
    import importlib
    import sys

    fake_st = _FakeStreamlit()
    fake_pio = SimpleNamespace(to_image=lambda fig, format="png": f"img-{format}".encode())

    class _FakeQrImage:
        def save(self, buffer):
            assert isinstance(buffer, io.BytesIO)
            buffer.write(b"qr-image")

    fake_qrcode = SimpleNamespace(make=lambda data: _FakeQrImage())

    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    if "ui_utils" in sys.modules:
        del sys.modules["ui_utils"]
    module = importlib.import_module("ui_utils")
    monkeypatch.setattr(module, "st", fake_st)
    monkeypatch.setattr(module, "pio", fake_pio)
    monkeypatch.setattr(module, "qrcode", fake_qrcode)
    return module, fake_st, tmp_path


def test_export_plotly_png_registers_download(ui_utils_module) -> None:
    module, fake_st, _ = ui_utils_module
    module.export_plotly_png(object(), filename="plot.png")
    assert fake_st.downloads[-1]["file_name"] == "plot.png"
    assert fake_st.downloads[-1]["mime"] == "image/png"


def test_export_plotly_svg_registers_download(ui_utils_module) -> None:
    module, fake_st, _ = ui_utils_module
    module.export_plotly_svg(object(), filename="plot.svg")
    assert fake_st.downloads[-1]["file_name"] == "plot.svg"
    assert fake_st.downloads[-1]["mime"] == "image/svg+xml"


def test_export_qr_code_warns_when_dependency_missing(monkeypatch) -> None:
    import importlib
    import sys

    fake_st = _FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    if "ui_utils" in sys.modules:
        del sys.modules["ui_utils"]
    module = importlib.import_module("ui_utils")
    monkeypatch.setattr(module, "st", fake_st)
    monkeypatch.setattr(module, "qrcode", None)

    module.export_qr_code("https://example.com")
    assert fake_st.warnings == ["qrcode non installé"]


def test_export_qr_code_renders_image_and_download_link(ui_utils_module) -> None:
    module, fake_st, _ = ui_utils_module
    module.export_qr_code("https://example.com")
    assert len(fake_st.images) == 1
    assert any("Télécharger QR" in markdown for markdown, _ in fake_st.markdowns)


def test_show_fallback_sends_warning(ui_utils_module) -> None:
    module, fake_st, _ = ui_utils_module
    module.show_fallback("fallback message")
    assert fake_st.warnings[-1] == "fallback message"


def test_show_tutorial_reads_markdown_or_falls_back(ui_utils_module) -> None:
    module, fake_st, tmp_path = ui_utils_module
    tutorial_path = tmp_path / "tutorial.md"
    tutorial_path.write_text("# Tutorial", encoding="utf-8")

    module.show_tutorial(str(tutorial_path))
    assert fake_st.markdowns[-1][0] == "# Tutorial"

    module.show_tutorial(str(tmp_path / "missing.md"))
    assert fake_st.infos[-1] == "Tutoriel non disponible."


def test_show_faq_reads_markdown_or_falls_back(ui_utils_module) -> None:
    module, fake_st, tmp_path = ui_utils_module
    faq_path = tmp_path / "faq.md"
    faq_path.write_text("# FAQ", encoding="utf-8")

    module.show_faq(str(faq_path))
    assert fake_st.markdowns[-1][0] == "# FAQ"

    module.show_faq(str(tmp_path / "missing_faq.md"))
    assert fake_st.infos[-1] == "FAQ non disponible."
