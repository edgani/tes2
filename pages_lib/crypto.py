"""crypto.py — Crypto page (with on-chain overlay)"""
from pages_lib.market_page_base import render_market_page

def render(snap):
    render_market_page(snap, "crypto", "Crypto", "₿", show_options=True, show_onchain=True)
