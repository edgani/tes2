from pages_lib.market_page_base import render_market_page

def render(snap):
    # Forex: COT + OI heatmap (no options/greeks)
    render_market_page(snap, "forex", "Forex", "💱", show_cot=True, show_oi=True)
