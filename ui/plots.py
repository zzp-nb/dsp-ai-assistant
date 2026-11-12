"""Matplotlib figures for the interactive DSP lab."""

from __future__ import annotations

import os
from pathlib import Path

_CACHE_DIR = Path(os.environ.get("MPLCONFIGDIR", Path(__file__).resolve().parents[1] / ".mplconfig"))
try:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(_CACHE_DIR))
except OSError:
    pass

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from dsp.convolution import ConvolutionResult
from dsp.fft import SpectrumResult
from dsp.filters import FilterDemo
from dsp.sampling import SamplingResult

PRIMARY = "#12355B"
ACCENT = "#2A9D8F"
WARM = "#D97757"
GOLD = "#C9963C"
GRID = "#DCE4EE"
MUTED = "#6B7A90"


def configure_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "#FFFFFF",
            "axes.facecolor": "#FFFFFF",
            "axes.edgecolor": "#CBD6E3",
            "axes.labelcolor": "#334155",
            "axes.titleweight": "semibold",
            "axes.titlesize": 11,
            "axes.labelsize": 9.5,
            "xtick.color": "#5D6B82",
            "ytick.color": "#5D6B82",
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "grid.color": GRID,
            "grid.linewidth": 0.7,
            "legend.fontsize": 8.5,
            "legend.frameon": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.family": "DejaVu Sans",
            "savefig.facecolor": "#FFFFFF",
        }
    )


def _grid(ax) -> None:
    ax.grid(True, linestyle="--", linewidth=0.7, alpha=0.65)


def sampling_figure(result: SamplingResult):
    configure_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.2, 5.6), constrained_layout=True)
    ax1.plot(result.time, result.continuous, color=PRIMARY, lw=1.5, label="Continuous x(t)")
    ax1.plot(result.time, result.reconstructed, color=ACCENT, lw=1.2, ls="--", label="Sinc reconstruction")
    step = max(1, result.sample_times.size // 120)
    ax1.scatter(
        result.sample_times[::step],
        result.samples[::step],
        s=22,
        color=WARM,
        edgecolor="white",
        linewidth=0.5,
        zorder=4,
        label=f"Samples (fs={result.fs:g} Hz)",
    )
    ax1.set_xlim(0, result.duration)
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Amplitude")
    ax1.set_title("Continuous signal, samples and band-limited reconstruction")
    ax1.legend(loc="upper right", ncol=2)
    _grid(ax1)
    if result.aliased:
        ax1.text(
            0.015,
            0.05,
            f"Aliasing: {result.f_signal:g} Hz appears at {result.alias_frequency:g} Hz",
            transform=ax1.transAxes,
            fontsize=9,
            color="#9A4A2F",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="#FDF0EA", edgecolor="#E8C2B2"),
        )

    markerline, stemlines, baseline = ax2.stem(
        result.sample_times[::step],
        result.samples[::step],
        linefmt="-",
        markerfmt="o",
        basefmt=" ",
    )
    plt.setp(stemlines, color=WARM, linewidth=1.0)
    plt.setp(markerline, color=WARM, markersize=4)
    ax2.set_xlim(0, result.duration)
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("x[n]")
    ax2.set_title("Discrete-time sequence actually available to the computer")
    _grid(ax2)
    return fig


def spectrum_figure(result: SpectrumResult):
    configure_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.2, 5.8), constrained_layout=True)
    ax1.plot(result.time, result.signal, color=PRIMARY, lw=1.1)
    ax1.set_xlim(0, result.time[-1])
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Amplitude")
    ax1.set_title(f"Time-domain signal (fs={result.fs:g} Hz, N={result.n})")
    _grid(ax1)

    ax2.plot(result.frequencies, result.magnitude, color=ACCENT, lw=1.3)
    _grid(ax2)
    if result.peaks:
        peak_freqs = [peak["frequency"] for peak in result.peaks]
        peak_amps = [peak["amplitude"] for peak in result.peaks]
        ax2.scatter(peak_freqs, peak_amps, color=WARM, zorder=5, s=28)
        for peak in result.peaks[:3]:
            ax2.annotate(
                f'{peak["frequency"]:.1f} Hz',
                (peak["frequency"], peak["amplitude"]),
                textcoords="offset points",
                xytext=(5, 7),
                fontsize=8,
                color="#9A4A2F",
            )
    ax2.set_xlim(0, result.fs / 2)
    ax2.set_xlabel("Frequency (Hz)")
    ax2.set_ylabel("Amplitude")
    ax2.set_title(f"One-sided amplitude spectrum · Δf = {result.resolution:.2f} Hz")
    return fig


def convolution_figure(result: ConvolutionResult):
    configure_style()
    fig, axes = plt.subplots(3, 1, figsize=(9.2, 6.0), constrained_layout=True)
    for ax, values, index, color, title in (
        (axes[0], result.x, result.n_x, PRIMARY, "Input sequence x[n]"),
        (axes[1], result.h, result.n_h, ACCENT, "Impulse response h[n]"),
        (axes[2], result.y, result.n_y, WARM, "Linear convolution y[n] = x[n] * h[n]"),
    ):
        markerline, stemlines, baseline = ax.stem(index, values, linefmt="-", markerfmt="o", basefmt=" ")
        plt.setp(stemlines, color=color, linewidth=1.2)
        plt.setp(markerline, color=color, markersize=5)
        ax.set_title(title)
        ax.set_xlabel("Sample index n")
        ax.set_ylabel("Amplitude")
        ax.set_xticks(index)
        _grid(ax)
    return fig


def filter_figure(demo: FilterDemo):
    configure_style()
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(9.2, 6.6), constrained_layout=True)
    ax1.plot(demo.time, demo.original, color="#8FA3BA", lw=1.0, label="Original")
    ax1.plot(demo.time, demo.filtered, color=WARM, lw=1.3, label="Filtered")
    ax1.set_xlim(0, demo.time[-1])
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Amplitude")
    ax1.set_title(f"Time domain · {demo.design.family} {demo.design.filter_type}")
    ax1.legend(loc="upper right", ncol=2)
    _grid(ax1)

    ax2.plot(demo.frequencies, demo.magnitude_db, color=PRIMARY, lw=1.4)
    for frequency in demo.design.cutoff:
        ax2.axvline(float(frequency), color=WARM, ls="--", lw=0.9, alpha=0.8)
    ax2.set_xlim(0, demo.design.fs / 2)
    ax2.set_ylim(max(-100, float(np.min(demo.magnitude_db)) - 5), 5)
    ax2.set_xlabel("Frequency (Hz)")
    ax2.set_ylabel("Magnitude (dB)")
    ax2.set_title("Magnitude response")
    _grid(ax2)

    ax3.plot(demo.frequencies, demo.phase_rad, color=ACCENT, lw=1.2)
    ax3.set_xlim(0, demo.design.fs / 2)
    ax3.set_xlabel("Frequency (Hz)")
    ax3.set_ylabel("Phase (rad)")
    ax3.set_title("Unwrapped phase response")
    _grid(ax3)
    return fig
