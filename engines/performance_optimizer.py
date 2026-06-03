"""engines/performance_optimizer.py -- Performance Optimization v1.0

Optimizes the macroregime pipeline:
  - Lazy engine loading (load on first use)
  - Tiered caching (memory LRU + disk JSON)
  - Parallel pipeline execution
  - Result memoization

Usage:
    from engines.performance_optimizer import LazyEngine, TieredCache, ParallelPipeline

    # Lazy engine
    rr_engine = LazyEngine("risk_range_engine", "RiskRangeEngine")
    result = rr_engine.run(prices)  # engine loaded on first call

    # Tiered cache
    cache = TieredCache()
    result = cache.get_or_compute("key", lambda: expensive_calc(), ttl=300)

    # Parallel pipeline
    pipeline = ParallelPipeline()
    results = pipeline.run_parallel([
        ("risk_range", risk_range_fn, prices),
        ("greeks", greeks_fn, prices),
        ("macro", macro_fn, fred),
    ])
"""

import functools
import hashlib
import json
import logging
import os
import pickle
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)

CACHE_DIR = "data/cache"
MEM_CACHE_SIZE = 128


class LazyEngine:
    """Lazy-load engine modules on first use.

    Engines are only imported and instantiated when first called,
    reducing startup time for pipelines with 59+ engines.

    Example:
        engine = LazyEngine("risk_range_engine", "RiskRangeEngine")
        result = engine.run(prices)   # loaded here
        result2 = engine.run(prices2) # reuse loaded instance
    """

    def __init__(self, module_name: str, class_name: str, *args, **kwargs):
        self.module_name = module_name
        self.class_name = class_name
        self._args = args
        self._kwargs = kwargs
        self._engine = None
        self._loaded = False

    def _load(self):
        """Import and instantiate the underlying engine (once)."""
        if self._loaded:
            return
        try:
            module = __import__(f"engines.{self.module_name}", fromlist=[self.class_name])
            cls = getattr(module, self.class_name)
            self._engine = cls(*self._args, **self._kwargs)
            self._loaded = True
            logger.info(f"Lazy-loaded {self.module_name}.{self.class_name}")
        except Exception as e:
            logger.error(f"Failed to lazy-load {self.module_name}: {e}")
            self._engine = None
            self._loaded = True

    # -- Public API --

    def __call__(self, *args, **kwargs):
        """Allow engine to be called directly:  engine(data)"""
        self._load()
        if self._engine is None:
            return {}
        return self._engine(*args, **kwargs)

    def __getattr__(self, name):
        """Delegate attribute access to the loaded engine."""
        self._load()
        if self._engine is None:
            return lambda *args, **kwargs: {}
        return getattr(self._engine, name)

    @property
    def is_loaded(self) -> bool:
        """Return whether the engine has been loaded (attempted)."""
        return self._loaded

    @property
    def engine_instance(self):
        """Return the underlying engine instance (forces load)."""
        self._load()
        return self._engine

    def reset(self):
        """Unload the engine (useful for testing / memory pressure)."""
        self._engine = None
        self._loaded = False
        logger.debug(f"Reset lazy engine {self.module_name}.{self.class_name}")


class TieredCache:
    """Two-tier cache: in-memory LRU + persistent disk JSON.

    Memory cache provides sub-millisecond lookups for hot data.
    Disk cache survives process restarts.

    Example:
        cache = TieredCache(cache_dir="data/cache", memory_size=128)

        # Manual get/set
        cache.set("risk_range:AAPL", result, ttl=600)
        result = cache.get("risk_range:AAPL")

        # Automatic compute-on-miss
        result = cache.get_or_compute(
            "greeks:AAPL",
            lambda: expensive_greeks_calc(aapl_data),
            ttl=300,
        )
    """

    def __init__(self, cache_dir: str = CACHE_DIR, memory_size: int = MEM_CACHE_SIZE):
        self.cache_dir = cache_dir
        self.memory_size = memory_size
        os.makedirs(cache_dir, exist_ok=True)
        # key -> (value, timestamp, ttl)
        self._mem_cache: Dict[str, Tuple[Any, float, float]] = {}
        # LRU tracking  (most recent at end)
        self._access_order: List[str] = []

    # -- Internal helpers --

    @staticmethod
    def _key(identifier: str) -> str:
        return hashlib.md5(identifier.encode()).hexdigest()

    def _disk_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, f"{key}.json")

    def _evict_if_needed(self):
        """Evict oldest entry if memory cache is at capacity."""
        if len(self._mem_cache) >= self.memory_size and self._access_order:
            oldest = self._access_order.pop(0)
            self._mem_cache.pop(oldest, None)
            logger.debug(f"LRU evicted {oldest}")

    def _touch(self, key: str):
        """Move key to most-recent position (MRU)."""
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    # -- Public API --

    def get(self, key: str) -> Optional[Any]:
        """Lookup by original key string. Returns None on miss or expiry."""
        k = self._key(key)
        now = time.time()

        # Tier 1: Memory
        if k in self._mem_cache:
            value, ts, ttl = self._mem_cache[k]
            if now - ts < ttl:
                self._touch(k)
                logger.debug(f"Memory cache hit: {key}")
                return value
            else:
                del self._mem_cache[k]
                self._access_order.remove(k)

        # Tier 2: Disk
        disk_path = self._disk_path(k)
        if os.path.exists(disk_path):
            try:
                with open(disk_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if now - data.get("timestamp", 0) < data.get("ttl", 0):
                    # Promote to memory
                    self._set_mem(k, data["value"], data["ttl"])
                    logger.debug(f"Disk cache hit (promoted): {key}")
                    return data["value"]
                else:
                    # Expired on disk -- clean it up
                    os.remove(disk_path)
            except Exception:
                pass

        logger.debug(f"Cache miss: {key}")
        return None

    def set(self, key: str, value: Any, ttl: float = 300):
        """Store value under key with time-to-live (seconds)."""
        k = self._key(key)
        self._set_mem(k, value, ttl)
        # Also write to disk for persistence
        try:
            disk_path = self._disk_path(k)
            with open(disk_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"value": value, "timestamp": time.time(), "ttl": ttl},
                    f,
                    default=str,
                )
        except Exception:
            pass

    def _set_mem(self, key: str, value: Any, ttl: float):
        """Insert/update memory cache entry."""
        if key not in self._mem_cache:
            self._evict_if_needed()
        self._mem_cache[key] = (value, time.time(), ttl)
        self._touch(key)

    def get_or_compute(self, key: str, compute_fn: Callable, ttl: float = 300) -> Any:
        """Return cached value if available; otherwise compute, store, and return."""
        cached = self.get(key)
        if cached is not None:
            return cached
        result = compute_fn()
        self.set(key, result, ttl)
        return result

    def invalidate(self, key: str):
        """Remove a single entry from both tiers."""
        k = self._key(key)
        self._mem_cache.pop(k, None)
        if k in self._access_order:
            self._access_order.remove(k)
        disk_path = self._disk_path(k)
        if os.path.exists(disk_path):
            os.remove(disk_path)

    def clear(self):
        """Clear memory cache only (disk cache persists)."""
        self._mem_cache.clear()
        self._access_order.clear()
        logger.info("Memory cache cleared")

    def clear_all(self):
        """Clear both memory and disk caches."""
        self.clear()
        for fn in os.listdir(self.cache_dir):
            if fn.endswith(".json"):
                os.remove(os.path.join(self.cache_dir, fn))
        logger.info("All caches cleared")

    @property
    def mem_size(self) -> int:
        """Current number of entries in memory cache."""
        return len(self._mem_cache)


class ParallelPipeline:
    """Execute independent pipeline steps in parallel using threads.

    Best for I/O-bound work (network calls, scrapers, file I/O).
    For CPU-bound work consider ProcessPoolExecutor instead.

    Example:
        pipeline = ParallelPipeline(max_workers=4)
        results = pipeline.run_parallel([
            ("risk_range",  calc_risk_range,  (prices,),  {}),
            ("greeks",      calc_greeks,      (ticker,),  {"refresh": True}),
            ("macro",       calc_macro,       (fred,),    {}),
        ])
        # results -> {"risk_range": {...}, "greeks": {...}, "macro": {...}}
    """

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def run_parallel(
        self,
        tasks: List[Tuple[str, Callable, Tuple, Dict]],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run tasks in parallel.

        Args:
            tasks: List of (name, function, args_tuple, kwargs_dict).
                   Use () for empty args and {{}} for empty kwargs.
            timeout: Optional per-task timeout in seconds.

        Returns:
            Dict mapping task name -> result.  Failed tasks return {{}}.
        """
        results: Dict[str, Any] = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(fn, *args, **kwargs): name
                for name, fn, args, kwargs in tasks
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=timeout)
                except Exception as e:
                    logger.error(f"Pipeline task '{name}' failed: {e}")
                    results[name] = {}

        return results

    def run_parallel_with_fallback(
        self,
        tasks: List[Tuple[str, Callable, Tuple, Dict]],
        fallback_fn: Callable = lambda: {},
    ) -> Dict[str, Any]:
        """Run tasks with a shared fallback value on any failure."""
        return self.run_parallel(
            [
                (name, self._wrap_with_fallback(fn, fallback_fn), args, kwargs)
                for name, fn, args, kwargs in tasks
            ]
        )

    @staticmethod
    def _wrap_with_fallback(fn: Callable, fallback: Callable) -> Callable:
        def wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Task failed, using fallback: {e}")
                return fallback()
        return wrapped
