"""Sampling, aliasing and sinc-reconstruction demonstrations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SamplingResult:
    time: np.ndarray
    continuous: np.ndarray
    sample_times: np.ndarray
    samples: np.ndarray
    reconstructed: np.ndarray
    f_signal: float
    fs: float
    nyquist: float
    alias_frequency: float
    aliased: bool
    sample_count: int
    duration: float


def alias_frequency(f_signal: float, fs: float) -> float:
    """Return the observed frequency in [0, fs/2] after sampling."""

    if fs <= 0:
        raise ValueError("采样频率必须大于 0。")
    folded = abs(f_signal - fs * round(f_signal / fs))
    return float(min(folded, fs / 2 + 1e-12))


def sinc_reconstruct(
    sample_times: np.ndarray,
    samples: np.ndarray,
    time: np.ndarray,
) -> np.ndarray:
    """Band-limited interpolation x(t) = Σ x[n] sinc((t-nTs)/Ts)."""

    if samples.size == 0:
        return np.zeros_like(time)
    ts = float(sample_times[1] - sample_times[0]) if sample_times.size > 1 else 1.0
    matrix = (time[:, None] - sample_times[None, :]) / ts
    return np.sinc(matrix) @ samples


def sampling_demo(
    *,
    f_signal: float = 5.0,
    fs: float = 40.0,
    duration: float = 0.4,
    phase: float = 0.0,
    amplitude: float = 1.0,
) -> SamplingResult:
    if not 0.1 <= f_signal <= 200:
        raise ValueError("信号频率需在 0.1–200 Hz 之间。")
    if not 1 <= fs <= 2000:
        raise ValueError("采样频率需在 1–2000 Hz 之间。")
    if not 0.05 <= duration <= 2.0:
        raise ValueError("观察时长需在 0.05–2.0 秒之间。")
    if amplitude <= 0:
        raise ValueError("幅度必须大于 0。")

    continuous_points = max(2000, min(20000, int(fs * duration * 20)))
    time = np.linspace(0.0, duration, continuous_points, endpoint=False)
    continuous = amplitude * np.sin(2 * np.pi * f_signal * time + phase)
    sample_times = np.arange(0.0, duration, 1.0 / fs)
    samples = amplitude * np.sin(2 * np.pi * f_signal * sample_times + phase)
    reconstructed = sinc_reconstruct(sample_times, samples, time)
    alias = alias_frequency(f_signal, fs)
    return SamplingResult(
        time=time,
        continuous=continuous,
        sample_times=sample_times,
        samples=samples,
        reconstructed=reconstructed,
        f_signal=float(f_signal),
        fs=float(fs),
        nyquist=float(fs / 2),
        alias_frequency=alias,
        aliased=bool(f_signal > fs / 2),
        sample_count=int(samples.size),
        duration=float(duration),
    )


def sampled_spectrum(samples: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """One-sided amplitude spectrum for a sampled real signal."""

    samples = np.asarray(samples, dtype=float)
    if samples.size < 4:
        raise ValueError("至少需要 4 个采样点。")
    window = np.hanning(samples.size)
    spectrum = np.fft.rfft(samples * window)
    frequencies = np.fft.rfftfreq(samples.size, d=1.0 / fs)
    amplitude = np.abs(spectrum) / max(window.sum(), 1e-12)
    amplitude[1:-1] *= 2.0
    return frequencies, amplitude
