from pages_lib.market_page_base import render_market_page

def render(snap):
    # Commodities: COT + OI heatmap ONLY (no options/greeks per Edward)
    render_market_page(snap, "commodity", "Commodities", "🛢️", show_cot=True, show_oi=True)
