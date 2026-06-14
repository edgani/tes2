"""
local_data_scraper.py — Jalanin di PC LU SENDIRI (bukan di Streamlit Cloud)
═══════════════════════════════════════════════════════════════════════════

KENAPA DI PC SENDIRI?
  barchart / cmegroup / laevitas block IP datacenter (Streamlit Cloud = datacenter).
  Tapi dari PC rumah lu (IP residential) + browser asli → mereka anggap lu manusia → lolos.

CARA KERJA:
  1. Script ini buka browser asli (Chromium) pakai Playwright
  2. Render halaman JS (kayak lu buka manual), ambil datanya
  3. Simpan ke file JSON (market_data.json)
  4. Push JSON ke GitHub repo lu (atau Google Drive)
  5. Dashboard Streamlit lu BACA JSON itu (bukan scrape langsung)

⚠️ ETIKA & ToS:
  - Ini buat PERSONAL USE (analisa lu sendiri), bukan jual-ulang data.
  - Kasih jeda (rate-limit) 3-5 detik antar halaman — jangan hammer server.
  - Cek ToS tiap situs. Kalau ada API resmi (Barchart OnDemand, Laevitas API,
    Unusual Whales), itu LEBIH BAIK & legal — bayar dikit tapi stabil.
  - Jangan scrape data berbayar yang di belakang login/paywall.
"""
import json
import time
import datetime as dt
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent / "market_data.json"
RATE_LIMIT_SEC = 4.0  # jeda antar halaman — JANGAN diturunin di bawah 3


def scrape_barchart_options(page, ticker: str) -> dict:
    """Ambil GEX / max-pain / put-call dari barchart (contoh: IBIT)."""
    url = f"https://www.barchart.com/etfs-funds/quotes/{ticker}/options-overview"
    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(2)  # kasih waktu JS render
    data = {"ticker": ticker, "source": "barchart"}
    try:
        # Barchart render data ke <table>. Ambil teks, parse manual.
        # NOTE: selector bisa berubah kalau barchart update layout — sesuaikan.
        rows = page.query_selector_all("div.bc-options-overview table tr")
        parsed = []
        for r in rows:
            cells = [c.inner_text().strip() for c in r.query_selector_all("td")]
            if cells:
                parsed.append(cells)
        data["raw_rows"] = parsed[:50]
    except Exception as e:
        data["error"] = str(e)
    return data


def scrape_cme_oi(page, product: str) -> dict:
    """CME OI profile. CmeWS endpoint 403 dari server, tapi dari browser bisa."""
    # CME QuikStrike butuh render penuh. Buka halaman tool-nya.
    url = f"https://www.cmegroup.com/markets/{product}.html"
    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(3)
    data = {"product": product, "source": "cme"}
    try:
        # Ambil tabel volume/OI yang ke-render
        body_text = page.inner_text("body")
        data["page_snippet"] = body_text[:2000]  # parse sesuai kebutuhan
    except Exception as e:
        data["error"] = str(e)
    return data


def scrape_laevitas_gex(page, asset: str = "BTC") -> dict:
    """Laevitas GEX (crypto). SPA — tunggu chart render."""
    url = f"https://app.laevitas.ch/dashboard/options/gex/{asset}/DERIBIT"
    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(5)  # SPA berat, kasih waktu lebih
    data = {"asset": asset, "source": "laevitas"}
    try:
        body_text = page.inner_text("body")
        data["page_snippet"] = body_text[:2000]
    except Exception as e:
        data["error"] = str(e)
    return data


def main():
    from playwright.sync_api import sync_playwright

    results = {"generated_at": dt.datetime.now().isoformat(), "data": {}}

    with sync_playwright() as p:
        # headless=False = browser keliatan (lebih lolos bot-detect saat awal).
        # Setelah yakin jalan, bisa headless=True.
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0 Safari/537.36"),
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()

        # ── Barchart: ETF options (yang ada di watchlist lu) ──
        for tkr in ["IBIT", "GLD", "USO", "SPY", "QQQ"]:
            try:
                results["data"][f"barchart_{tkr}"] = scrape_barchart_options(page, tkr)
                print(f"✓ barchart {tkr}")
            except Exception as e:
                print(f"✗ barchart {tkr}: {e}")
            time.sleep(RATE_LIMIT_SEC)

        # ── CME: futures OI ──
        for prod in ["crude-oil", "gold", "silver"]:
            try:
                results["data"][f"cme_{prod}"] = scrape_cme_oi(page, prod)
                print(f"✓ cme {prod}")
            except Exception as e:
                print(f"✗ cme {prod}: {e}")
            time.sleep(RATE_LIMIT_SEC)

        # ── Laevitas: crypto GEX ──
        for asset in ["BTC", "ETH"]:
            try:
                results["data"][f"laevitas_{asset}"] = scrape_laevitas_gex(page, asset)
                print(f"✓ laevitas {asset}")
            except Exception as e:
                print(f"✗ laevitas {asset}: {e}")
            time.sleep(RATE_LIMIT_SEC)

        browser.close()

    OUTPUT_FILE.write_text(json.dumps(results, indent=2))
    print(f"\n✅ Saved → {OUTPUT_FILE}")
    print("Next: commit & push market_data.json ke GitHub repo lu, "
          "atau upload ke Google Drive, lalu dashboard baca file ini.")


if __name__ == "__main__":
    main()
