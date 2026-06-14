"""ihsg.py — IHSG page (with bandar/cornering overlay, NO options)"""
from pages_lib.market_page_base import render_market_page

def render(snap):
    render_market_page(snap, "ihsg", "IHSG (Indonesia)", "🇮🇩", show_options=False, show_bandar=True)
