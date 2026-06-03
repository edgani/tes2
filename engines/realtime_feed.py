"""engines/realtime_feed.py -- Real-time Price Feed Framework v1.0

Provides live price streaming for all markets:
  - US Stocks: Webull, Yahoo Finance (delay 15min free, real-time with premium)
  - Crypto: Binance WebSocket, Coinbase
  - Forex: OANDA, Forex.com
  - Commodities: Delayed quotes via Yahoo
  - IHSG: RTI/BEI (delayed)

Usage:
    from engines.realtime_feed import RealtimeFeed
    feed = RealtimeFeed()
    
    # Subscribe to tickers
    feed.subscribe(["AAPL", "BTC-USD", "EURUSD=X"])
    
    # Get latest prices
    prices = feed.get_prices()
    # {"AAPL": 195.50, "BTC-USD": 67500, "EURUSD=X": 1.0850}
    
    # Or use callback
    feed.on_price_update = lambda ticker, price: print(f"{ticker}: {price}")
    
    # Stop
    feed.stop()
"""
import asyncio
import json
import logging
import threading
import time
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque

import requests
import websocket

logger = logging.getLogger(__name__)


@dataclass
class PriceUpdate:
    ticker: str
    price: float
    bid: float = 0.0
    ask: float = 0.0
    volume: float = 0.0
    timestamp: float = 0.0
    source: str = ""


class RealtimeFeed:
    """Unified real-time price feed manager."""
    
    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self._subscribed: set = set()
        self._prices: Dict[str, PriceUpdate] = {}
        self._callbacks: List[Callable] = []
        self._running = False
        self._threads: List[threading.Thread] = []
        self._lock = threading.Lock()
        self.on_price_update: Optional[Callable[[str, float], None]] = None
    
    def subscribe(self, tickers: List[str]):
        """Subscribe to real-time price updates for tickers."""
        self._subscribed.update(t.upper() for t in tickers)
        if self._running:
            self._restart_feeds()
    
    def unsubscribe(self, tickers: List[str]):
        """Unsubscribe from tickers."""
        for t in tickers:
            self._subscribed.discard(t.upper())
    
    def get_prices(self) -> Dict[str, float]:
        """Get latest prices for all subscribed tickers."""
        with self._lock:
            return {t: p.price for t, p in self._prices.items()}
    
    def get_price(self, ticker: str) -> Optional[float]:
        """Get latest price for a single ticker."""
        with self._lock:
            p = self._prices.get(ticker.upper())
            return p.price if p else None
    
    def start(self):
        """Start all feed threads."""
        if self._running:
            return
        self._running = True
        self._start_polling_feed()  # Always works (polling)
        # Try WebSocket for crypto
        if any(t.endswith(("-USD", "-USDT")) for t in self._subscribed):
            self._start_binance_ws()
    
    def stop(self):
        """Stop all feeds."""
        self._running = False
        for t in self._threads:
            t.join(timeout=2)
        self._threads.clear()
    
    # -- Binance WebSocket (Crypto) -----------------------------
    
    def _start_binance_ws(self):
        """Start Binance WebSocket for crypto prices."""
        def on_message(ws, message):
            try:
                data = json.loads(message)
                s = data.get("s", "")
                c = float(data.get("c", 0))
                if s and c:
                    ticker = f"{s[:-4]}-USD" if s.endswith("USDT") else s
                    self._update_price(ticker, c, "binance_ws")
            except Exception:
                pass
        
        def run_ws():
            # Build stream names
            streams = []
            for t in self._subscribed:
                if "-USD" in t or "-USDT" in t:
                    symbol = t.replace("-USD", "USDT").replace("-USDT", "USDT")
                    streams.append(f"{symbol.lower()}@ticker")
            if not streams:
                return
            url = f"wss://stream.binance.com:9443/ws/{'/'.join(streams[:10])}"
            ws = websocket.WebSocketApp(url, on_message=on_message)
            ws.run_forever()
        
        t = threading.Thread(target=run_ws, daemon=True)
        t.start()
        self._threads.append(t)
    
    # -- Polling Feed (Universal fallback) -----------------------
    
    def _start_polling_feed(self):
        """Start polling thread -- works for all markets."""
        def poll_loop():
            while self._running:
                try:
                    self._poll_yahoo()
                except Exception as e:
                    logger.debug(f"Poll error: {e}")
                time.sleep(5)  # 5-second intervals
        
        t = threading.Thread(target=poll_loop, daemon=True)
        t.start()
        self._threads.append(t)
    
    def _poll_yahoo(self):
        """Poll Yahoo Finance for latest prices."""
        if not self._subscribed:
            return
        # Batch tickers into groups of 50
        tickers = list(self._subscribed)
        for i in range(0, len(tickers), 50):
            batch = tickers[i:i+50]
            try:
                import yfinance as yf
                data = yf.download(batch, period="1d", interval="1m", 
                                progress=False, threads=True)
                if data is not None and not data.empty:
                    for ticker in batch:
                        try:
                            price = data["Close"][ticker].dropna().iloc[-1]
                            self._update_price(ticker, float(price), "yahoo_poll")
                        except Exception:
                            pass
            except Exception:
                pass
    
    def _update_price(self, ticker: str, price: float, source: str):
        """Thread-safe price update."""
        with self._lock:
            self._prices[ticker.upper()] = PriceUpdate(
                ticker=ticker.upper(), price=price, 
                timestamp=time.time(), source=source
            )
        if self.on_price_update:
            try:
                self.on_price_update(ticker.upper(), price)
            except Exception:
                pass
    
    def _restart_feeds(self):
        """Restart feeds with new subscription list."""
        self.stop()
        time.sleep(1)
        self.start()
