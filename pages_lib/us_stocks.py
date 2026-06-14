"""us_stocks.py — US Stocks page (with options overlay)"""
from pages_lib.market_page_base import render_market_page

def render(snap):
    render_market_page(snap, "us_equity", "US Stocks", "🇺🇸", show_options=True)
