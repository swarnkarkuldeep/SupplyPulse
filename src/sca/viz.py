"""Shared chart style: one palette, one look, insight-first titles."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Okabe-Ito palette: distinguishable under the common forms of colour blindness.
PALETTE = {
    "blue": "#0072B2",
    "orange": "#E69F00",
    "green": "#009E73",
    "red": "#D55E00",
    "sky": "#56B4E9",
    "pink": "#CC79A7",
    "yellow": "#F0E442",
    "grey": "#6B7280",
}
CATEGORICAL = list(PALETTE.values())[:7]


def apply_style() -> None:
    """Apply the project-wide matplotlib style."""
    plt.rcParams.update(
        {
            "figure.figsize": (9, 4.8),
            "figure.dpi": 110,
            "savefig.dpi": 150,
            "axes.prop_cycle": matplotlib.cycler(color=CATEGORICAL),
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": "#E5E7EB",
            "grid.linewidth": 0.8,
            "axes.axisbelow": True,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 10,
            "font.size": 10,
            "legend.frameon": False,
        }
    )


def save_fig(fig: plt.Figure, path: str | Path) -> Path:
    """Save a figure (creating folders) and close it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


apply_style()
