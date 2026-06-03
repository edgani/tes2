"""engines/chart_engine.py -- Professional Financial Chart Engine v1.0

All charts use dark theme (#0D1117 bg, #E6EDF3 text).
Returns PNG bytes for st.image() in Streamlit.

Usage:
    from engines.chart_engine import (
        render_gauge, render_sparkline, render_cot_bars,
        render_donut, render_heatmap, render_stacked_bar,
        render_vol_surface, render_multi_sparklines
    )

    # Gauge chart for VIX
    img = render_gauge(value=16.7, min_val=0, max_val=40,
                       title="VIX", color="#3FB950",
                       zones=[(0,18,"green"),(18,25,"yellow"),(25,40,"red")])
    st.image(img, use_column_width=True)
"""
import io
import base64
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Wedge
import matplotlib.patches as mpatches
from typing import List, Dict, Tuple, Optional, Union

# Dark theme defaults
DARK_BG = '#0D1117'
DARK_CARD = '#161B22'
TEXT_COLOR = '#E6EDF3'
TEXT_SECONDARY = '#8B949E'
GRID_COLOR = '#21262D'
GREEN = '#3FB950'
RED = '#F85149'
YELLOW = '#D29922'
BLUE = '#58A6FF'

plt.rcParams.update({
    'figure.facecolor': DARK_BG,
    'axes.facecolor': DARK_BG,
    'axes.edgecolor': GRID_COLOR,
    'axes.labelcolor': TEXT_COLOR,
    'text.color': TEXT_COLOR,
    'xtick.color': TEXT_SECONDARY,
    'ytick.color': TEXT_SECONDARY,
    'grid.color': GRID_COLOR,
    'grid.alpha': 0.3,
})


def _fig_to_bytes(fig, dpi=120) -> bytes:
    """Convert matplotlib figure to PNG bytes."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor=DARK_BG, edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_gauge(value: float, min_val: float, max_val: float,
                 title: str = "", color: str = GREEN,
                 zones: Optional[List[Tuple[float, float, str]]] = None,
                 width: int = 3, height: int = 2) -> bytes:
    """
    Render a semicircular gauge chart.

    Args:
        value: Current value
        min_val: Minimum of gauge range
        max_val: Maximum of gauge range
        title: Title text (displayed above gauge)
        color: Color for the value arc
        zones: List of (start, end, color) for background zones
        width: Figure width in inches
        height: Figure height in inches

    Returns:
        PNG image bytes
    """
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-0.3, 1.2)
    ax.axis('off')

    # Background arc zones
    if zones:
        for zstart, zend, zcolor in zones:
            zstart_angle = 180 - (zstart - min_val) / (max_val - min_val) * 180
            zend_angle = 180 - (zend - min_val) / (max_val - min_val) * 180
            theta = np.linspace(np.radians(zend_angle), np.radians(zstart_angle), 50)
            x = 0.9 * np.cos(theta)
            y = 0.9 * np.sin(theta)
            ax.fill_between(x, 0, y, color=zcolor, alpha=0.15)

    # Value arc
    pct = (value - min_val) / (max_val - min_val)
    end_angle = 180 - pct * 180
    theta = np.linspace(np.radians(180), np.radians(end_angle), 100)
    x = 0.9 * np.cos(theta)
    y = 0.9 * np.sin(theta)
    ax.plot(x, y, color=color, linewidth=8, solid_capstyle='round')

    # Center text
    ax.text(0, 0.15, f"{value:.1f}", ha='center', va='center',
            fontsize=22, fontweight='bold', color=color)
    if title:
        ax.text(0, 0.65, title, ha='center', va='center',
                fontsize=9, color=TEXT_SECONDARY, fontweight='600')

    # Min/Max labels
    ax.text(-0.95, -0.1, f"{min_val:.0f}", ha='center', fontsize=7, color=TEXT_SECONDARY)
    ax.text(0.95, -0.1, f"{max_val:.0f}", ha='center', fontsize=7, color=TEXT_SECONDARY)

    return _fig_to_bytes(fig)


def render_sparkline(data: List[float], color: str = GREEN,
                     width: int = 3, height: int = 1,
                     title: str = "") -> bytes:
    """
    Render a mini sparkline chart.

    Args:
        data: List of values (price history)
        color: Line color
        width/height: Figure size in inches
        title: Optional title

    Returns:
        PNG image bytes
    """
    fig, ax = plt.subplots(figsize=(width, height))
    ax.plot(data, color=color, linewidth=1.5)
    ax.fill_between(range(len(data)), data, data[0], alpha=0.1, color=color)
    ax.axis('off')
    if title:
        ax.text(0.02, 0.95, title, transform=ax.transAxes, fontsize=7,
                color=TEXT_SECONDARY, va='top')
    plt.tight_layout(pad=0.1)
    return _fig_to_bytes(fig)


def render_multi_sparklines(ticker_data: Dict[str, List[float]],
                            width: int = 10, height_per_row: int = 0.6) -> bytes:
    """
    Render multiple sparklines stacked vertically.

    Args:
        ticker_data: Dict of {ticker: [price_history]}
        width: Figure width in inches
        height_per_row: Height per sparkline in inches

    Returns:
        PNG image bytes
    """
    n = len(ticker_data)
    fig, axes = plt.subplots(n, 1, figsize=(width, n * height_per_row),
                             sharex=True)
    if n == 1:
        axes = [axes]

    for ax, (ticker, data) in zip(axes, ticker_data.items()):
        ret = (data[-1] / data[0] - 1) * 100 if data and data[0] else 0
        color = GREEN if ret >= 0 else RED
        ax.plot(data, color=color, linewidth=1)
        ax.fill_between(range(len(data)), data, data[0], alpha=0.08, color=color)
        ax.text(0.02, 0.5, ticker, transform=ax.transAxes, fontsize=8,
                color=TEXT_COLOR, va='center', fontweight='bold')
        ax.text(0.98, 0.5, f"{ret:+.1f}%", transform=ax.transAxes, fontsize=8,
                color=color, va='center', ha='right', fontweight='bold')
        ax.axis('off')

    plt.tight_layout(pad=0.1)
    return _fig_to_bytes(fig)


def render_cot_bars(contracts: Dict[str, Dict], width: int = 8, height: int = 4) -> bytes:
    """
    Render COT positioning as horizontal bar chart.

    Args:
        contracts: Dict of {contract: {"non_commercial_net": X, "commercial_net": Y}}
        width/height: Figure size

    Returns:
        PNG image bytes
    """
    fig, ax = plt.subplots(figsize=(width, height))
    names = list(contracts.keys())
    spec = [c.get("non_commercial_net", 0) for c in contracts.values()]
    comm = [c.get("commercial_net", 0) for c in contracts.values()]

    y = np.arange(len(names))
    h = 0.35
    ax.barh(y + h / 2, spec, h, label='Speculators', color=BLUE, alpha=0.8)
    ax.barh(y - h / 2, comm, h, label='Commercial', color=GREEN, alpha=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.axvline(x=0, color=TEXT_SECONDARY, linewidth=0.5)
    ax.legend(fontsize=7, loc='lower right')
    ax.set_xlabel('Net Position (contracts)', fontsize=8, color=TEXT_SECONDARY)
    plt.tight_layout()
    return _fig_to_bytes(fig)


def render_donut(labels: List[str], values: List[float],
                 width: int = 4, height: int = 4) -> bytes:
    """
    Render donut chart for portfolio allocation.

    Args:
        labels: Category labels
        values: Values (percentages)
        width/height: Figure size

    Returns:
        PNG image bytes
    """
    colors_pie = [GREEN, RED, YELLOW, BLUE, '#A371F7', '#F0883E', '#56D364']
    fig, ax = plt.subplots(figsize=(width, height))
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct='%1.0f%%', startangle=90,
        colors=colors_pie[:len(labels)], pctdistance=0.75,
        textprops={'fontsize': 8, 'color': TEXT_COLOR}
    )
    for autotext in autotexts:
        autotext.set_fontsize(7)
        autotext.set_fontweight('bold')
    # Donut hole
    centre_circle = plt.Circle((0, 0), 0.50, fc=DARK_BG)
    ax.add_artist(centre_circle)
    ax.set_aspect('equal')
    plt.tight_layout()
    return _fig_to_bytes(fig)


def render_heatmap(data: np.ndarray, labels: List[str],
                   width: int = 6, height: int = 5) -> bytes:
    """
    Render correlation matrix heatmap.

    Args:
        data: 2D numpy array (correlation matrix)
        labels: Tickers/names for axes
        width/height: Figure size

    Returns:
        PNG image bytes
    """
    fig, ax = plt.subplots(figsize=(width, height))
    im = ax.imshow(data, cmap='RdYlGn', vmin=-1, vmax=1, aspect='auto')
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=7)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=7)
    # Add text annotations
    for i in range(len(labels)):
        for j in range(len(labels)):
            text_color = '#0D1117' if abs(data[i, j]) > 0.5 else TEXT_COLOR
            ax.text(j, i, f'{data[i, j]:.2f}', ha='center', va='center',
                    fontsize=6, color=text_color)
    plt.colorbar(im, ax=ax, shrink=0.8).ax.tick_params(labelsize=7)
    plt.tight_layout()
    return _fig_to_bytes(fig)


def render_stacked_bar(categories: List[str], values: List[List[float]],
                       colors: List[str], width: int = 6, height: int = 3) -> bytes:
    """
    Render horizontal stacked bar chart.

    Args:
        categories: Category labels (y-axis)
        values: List of value lists (one per segment)
        colors: Colors for each segment
        width/height: Figure size

    Returns:
        PNG image bytes
    """
    fig, ax = plt.subplots(figsize=(width, height))
    y = np.arange(len(categories))
    left = np.zeros(len(categories))
    for vals, color in zip(values, colors):
        ax.barh(y, vals, left=left, color=color, alpha=0.85, height=0.6)
        left += np.array(vals)
    ax.set_yticks(y)
    ax.set_yticklabels(categories, fontsize=8)
    ax.set_xlabel('%', fontsize=8, color=TEXT_SECONDARY)
    plt.tight_layout()
    return _fig_to_bytes(fig)


def render_vol_surface(strikes: List[float], expiries: List[str],
                       ivs: np.ndarray, width: int = 6, height: int = 4) -> bytes:
    """
    Render volatility surface as 3D-ish 2D contour plot.

    Args:
        strikes: Strike prices
        expiries: Expiration labels
        ivs: 2D array of IV values [strikes x expiries]
        width/height: Figure size

    Returns:
        PNG image bytes
    """
    fig, ax = plt.subplots(figsize=(width, height))
    X, Y = np.meshgrid(range(len(expiries)), strikes)
    cs = ax.contourf(X, Y, ivs, levels=20, cmap='viridis')
    ax.set_xticks(range(len(expiries)))
    ax.set_xticklabels(expiries, rotation=45, fontsize=7)
    ax.set_ylabel('Strike', fontsize=8, color=TEXT_SECONDARY)
    plt.colorbar(cs, ax=ax, shrink=0.8).ax.tick_params(labelsize=7)
    plt.tight_layout()
    return _fig_to_bytes(fig)
