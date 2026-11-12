"""FFT-based spectrum analysis helpers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks, get_window


@dataclass
class SpectrumResult:
    time: np.ndarray
    signal: np.ndarray
    frequencies: np.ndarray
    magnitude: np.ndarray
    phase: np.ndarray
    fs: float
    n: int
    peaks: list[dict]
    resolution: float


def make_multitone(
    freqs: list[float],
    amplitudes: list[float] | None = None,
    *,
    fs: float = 1000.0,
    duration: float = 0.5,
    noise: float = 0.0,
    phases: list[float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if not freqs:
        raise ValueError("至少需要一个频率分量。")
    if fs <= 0 or duration <= 0:
        raise ValueError("采样率和时长必须大于 0。")
    nyquist = fs / 2
    if any(f <= 0 or f >= nyquist for f in freqs):
        raise ValueError(f"所有频率必须大于 0 且小于奈奎斯特频率 {nyquist:g} Hz。")
    amplitudes = amplitudes or [1.0] * len(freqs)
    if len(amplitudes) != len(freqs):
        raise ValueError("频率与幅度数量必须一致。")
    phases = phases or [0.0] * len(freqs)
    n = max(32, int(round(fs * duration)))
    t = np.arange(n) / fs
    signal = np.zeros(n, dtype=float)
    for frequency, amplitude, phase in zip(freqs, amplitudes, phases):
        signal += amplitude * np.sin(2 * np.pi * frequency * t + phase)
    if noise > 0:
        signal += np.random.default_rng(42).normal(0, noise, n)
    return t, signal


def compute_spectrum(signal: np.ndarray, fs: float, *, window: str = "hann") -> SpectrumResult:
    signal = np.asarray(signal, dtype=float).ravel()
    n = signal.size
    if n < 8:
        raise ValueError("信号长度至少为 8 个采样点。")
    if fs <= 0:
        raise ValueError("采样率必须大于 0。")
    if window not in {"hann", "hamming", "blackman", "rectangular"}:
        raise ValueError("不支持的窗函数。")
    if window == "rectangular":
        window_values = np.ones(n)
    else:
        window_values = get_window(window, n, fftbins=True)
    windowed = signal - np.mean(signal)
    windowed = windowed * window_values
    spectrum = np.fft.rfft(windowed)
    frequencies = np.fft.rfftfreq(n, d=1.0 / fs)
    magnitude = np.abs(spectrum) / max(window_values.sum(), 1e-12)
    magnitude[1:-1] *= 2.0
    phase = np.angle(spectrum)
    resolution = fs / n
    peaks = _top_peaks(frequencies, magnitude, resolution)
    return SpectrumResult(
        time=np.arange(n) / fs,
        signal=signal,
        frequencies=frequencies,
        magnitude=magnitude,
        phase=phase,
        fs=float(fs),
        n=n,
        peaks=peaks,
        resolution=float(resolution),
    )


def _top_peaks(frequencies: np.ndarray, magnitude: np.ndarray, resolution: float) -> list[dict]:
    if magnitude.size < 3:
        return []
    max_amp = float(magnitude.max())
    if max_amp <= 0:
        return []
    indices, properties = find_peaks(magnitude, height=max_amp * 0.12, distance=max(1, int(2 / max(resolution, 1e-9))))
    ranked = sorted(indices, key=lambda index: magnitude[index], reverse=True)[:4]
    return [
        {
            "frequency": float(frequencies[index]),
            "amplitude": float(magnitude[index]),
            "relative_db": float(20 * np.log10(max(magnitude[index], 1e-12) / max_amp)),
        }
        for index in ranked
    ]


def zero_pad_spectrum(signal: np.ndarray, fs: float, factor: int = 4) -> tuple[np.ndarray, np.ndarray]:
    signal = np.asarray(signal, dtype=float)
    if factor < 1 or factor > 32:
        raise ValueError("补零倍数需在 1–32 之间。")
    n = signal.size * factor
    spectrum = np.fft.rfft(signal, n=n)
    frequencies = np.fft.rfftfreq(n, d=1.0 / fs)
    return frequencies, np.abs(spectrum) / signal.size
