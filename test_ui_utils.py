import plotly.graph_objs as go
import pytest
import streamlit as st

from ui_utils import (export_plotly_png, export_plotly_svg, export_qr_code,
                      show_fallback, show_faq, show_tutorial)


def test_export_png(tmp_path):
    fig = go.Figure()
    fig.add_scatter3d(x=[1, 2], y=[3, 4], z=[5, 6])
    # Just check no exception (Streamlit download_button is UI, not testable headless)
    export_plotly_png(fig)


def test_export_svg(tmp_path):
    fig = go.Figure()
    fig.add_scatter3d(x=[1, 2], y=[3, 4], z=[5, 6])
    export_plotly_svg(fig)


def test_qr_code():
    export_qr_code("https://example.com")


def test_fallback():
    show_fallback()


def test_tutorial():
    show_tutorial()


def test_faq():
    show_faq()
