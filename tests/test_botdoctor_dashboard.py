"""Tests unitaires — botdoctor_dashboard.render() sans serveur Streamlit."""

from __future__ import annotations

import sys
import pytest
from unittest.mock import MagicMock, patch


def _make_st_mock():
    return MagicMock()


@pytest.fixture(autouse=True)
def mock_streamlit():
    st_mock = _make_st_mock()
    with patch.dict(sys.modules, {"streamlit": st_mock}):
        if "supervision.botdoctor_dashboard" in sys.modules:
            del sys.modules["supervision.botdoctor_dashboard"]
        yield st_mock


@pytest.fixture
def healthy_doctor():
    doc = MagicMock()
    doc.get_report.return_value = [
        {"name": "market_scanner", "is_healthy": True, "error": None},
        {"name": "execution_engine", "is_healthy": True, "error": None},
    ]
    return doc


@pytest.fixture
def unhealthy_doctor():
    doc = MagicMock()
    doc.get_report.return_value = [
        {"name": "risk_monitor", "is_healthy": False, "error": "timeout"},
        {"name": "trade_logger", "is_healthy": True, "error": None},
    ]
    return doc


class TestRenderNoneDoctor:
    def test_render_none_calls_markdown_title(self, mock_streamlit):
        from supervision.botdoctor_dashboard import render
        render(None)
        mock_streamlit.markdown.assert_called()

    def test_render_none_calls_info(self, mock_streamlit):
        from supervision.botdoctor_dashboard import render
        render(None)
        mock_streamlit.info.assert_called_once()

    def test_render_no_args_calls_info(self, mock_streamlit):
        from supervision.botdoctor_dashboard import render
        render()
        mock_streamlit.info.assert_called_once()

    def test_render_none_does_not_call_get_report(self, mock_streamlit):
        from supervision.botdoctor_dashboard import render
        doctor = MagicMock()
        render(None)
        doctor.get_report.assert_not_called()


class TestRenderHealthyDoctor:
    def test_render_calls_get_report(self, mock_streamlit, healthy_doctor):
        from supervision.botdoctor_dashboard import render
        render(healthy_doctor)
        healthy_doctor.get_report.assert_called_once()

    def test_render_calls_markdown_for_each_status(self, mock_streamlit, healthy_doctor):
        from supervision.botdoctor_dashboard import render
        render(healthy_doctor)
        assert mock_streamlit.markdown.call_count >= 3

    def test_render_healthy_module_contains_checkmark(self, mock_streamlit, healthy_doctor):
        from supervision.botdoctor_dashboard import render
        render(healthy_doctor)
        calls = [str(c) for c in mock_streamlit.markdown.call_args_list]
        status_calls = [c for c in calls if "market_scanner" in c or "execution_engine" in c]
        assert any("✅" in c for c in status_calls)

    def test_render_does_not_call_info_when_doctor_given(self, mock_streamlit, healthy_doctor):
        from supervision.botdoctor_dashboard import render
        render(healthy_doctor)
        mock_streamlit.info.assert_not_called()


class TestRenderUnhealthyDoctor:
    def test_render_unhealthy_module_contains_cross(self, mock_streamlit, unhealthy_doctor):
        from supervision.botdoctor_dashboard import render
        render(unhealthy_doctor)
        calls = [str(c) for c in mock_streamlit.markdown.call_args_list]
        status_calls = [c for c in calls if "risk_monitor" in c]
        assert any("❌" in c for c in status_calls)

    def test_render_shows_error_message(self, mock_streamlit, unhealthy_doctor):
        from supervision.botdoctor_dashboard import render
        render(unhealthy_doctor)
        calls = [str(c) for c in mock_streamlit.markdown.call_args_list]
        assert any("timeout" in c for c in calls)

    def test_render_mixed_shows_both_icons(self, mock_streamlit, unhealthy_doctor):
        from supervision.botdoctor_dashboard import render
        render(unhealthy_doctor)
        calls = [str(c) for c in mock_streamlit.markdown.call_args_list]
        assert any("✅" in c for c in calls) and any("❌" in c for c in calls)


class TestRenderEdgeCases:
    def test_render_empty_report(self, mock_streamlit):
        from supervision.botdoctor_dashboard import render
        doctor = MagicMock()
        doctor.get_report.return_value = []
        render(doctor)
        doctor.get_report.assert_called_once()

    def test_render_module_with_no_error_key(self, mock_streamlit):
        from supervision.botdoctor_dashboard import render
        doctor = MagicMock()
        doctor.get_report.return_value = [{"name": "x", "is_healthy": True}]
        render(doctor)
