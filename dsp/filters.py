"""FIR / IIR filter design and demonstration helpers using SciPy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy import signal


@dataclass
class FilterDesign:
    b: np.ndarray
    a: np.ndarray
    family: str
    filter_type: str
    fs: float
    cutoff: tuple[float, ...]
    order: int
    coefficients_label: str


@dataclass
class FilterDemo:
    design: FilterDesign
    time: np.ndarray
    original: np.ndarray
    filtered: np.ndarray
    frequencies: np.ndarray
    magnitude_db: np.ndarray
    phase_rad: np.ndarray


def _normalised_cutoff(
    cutoff: float | tuple[float, float] | list[float],
    fs: float,
    filter_type: str,
) -> float | tuple[float, float]:
    if fs <= 0:
        raise ValueError("采样频率必须大于 0。")
    nyquist = fs / 2
    if filter_type in {"lowpass", "highpass"}:
        if isinstance(cutoff, (tuple, list)):
            value = float(cutoff[0]) if cutoff else 0.0
        else:
            value = float(cutoff)
        if not 0 < value < nyquist:
            raise ValueError(f"截止频率必须在 0 与奈奎斯特频率 {nyquist:g} Hz 之间。")
        return value / nyquist
    if isinstance(cutoff, (tuple, list)):
        if len(cutoff) != 2:
            raise ValueError("带通/带阻需要两个截止频率。")
        low, high = float(cutoff[0]), float(cutoff[1])
    else:
        raise ValueError("带通/带阻需要两个截止频率。")
    if not 0 < low < high < nyquist:
        raise ValueError("截止频率需满足 0 < 低端 < 高端 < 奈奎斯特频率。")
    return low / nyquist, high / nyquist


def design_fir(
    *,
    filter_type: Literal["lowpass", "highpass", "bandpass", "bandstop"] = "lowpass",
    cutoff: float | tuple[float, float] = 100.0,
    fs: float = 1000.0,
    num_taps: int = 51,
    window: str = "hamming",
) -> FilterDesign:
    if num_taps < 5 or num_taps > 501:
        raise ValueError("FIR 阶数（抽头数）需在 5–501 之间。")
    if num_taps % 2 == 0 and filter_type == "highpass":
        raise ValueError("高通 FIR 的抽头数必须为奇数，避免 Nyquist 处增益异常。")
    normalised = _normalised_cutoff(cutoff, fs, filter_type)
    b = signal.firwin(
        num_taps,
        normalised,
        window=window,
        pass_zero=(filter_type in {"lowpass", "bandstop"}),
    )
    a = np.array([1.0])
    return FilterDesign(
        b=b,
        a=a,
        family="FIR",
        filter_type=filter_type,
        fs=float(fs),
        cutoff=tuple(np.atleast_1d(cutoff)),
        order=num_taps - 1,
        coefficients_label=f"{num_taps} 抽头，{window} 窗",
    )


def design_iir(
    *,
    filter_type: Literal["lowpass", "highpass", "bandpass", "bandstop"] = "lowpass",
    cutoff: float | tuple[float, float] = 100.0,
    fs: float = 1000.0,
    order: int = 4,
    family: Literal["butter", "cheby1"] = "butter",
    ripple_db: float = 1.0,
) -> FilterDesign:
    if order < 1 or order > 10:
        raise ValueError("IIR 阶数需在 1–10 之间。")
    normalised = _normalised_cutoff(cutoff, fs, filter_type)
    if family == "butter":
        b, a = signal.butter(order, normalised, btype=filter_type, output="ba")
        label = f"Butterworth 阶数 {order}"
    elif family == "cheby1":
        b, a = signal.cheby1(order, ripple_db, normalised, btype=filter_type, output="ba")
        label = f"Chebyshev I 阶数 {order}，纹波 {ripple_db:g} dB"
    else:
        raise ValueError("当前支持 butter 与 cheby1 两种 IIR 设计。")
    return FilterDesign(
        b=b,
        a=a,
        family="IIR",
        filter_type=filter_type,
        fs=float(fs),
        cutoff=tuple(np.atleast_1d(cutoff)),
        order=order,
        coefficients_label=label,
    )


def frequency_response(
    design: FilterDesign, *, points: int = 2048
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = max(256, min(int(points), 8192))
    frequencies, response = signal.freqz(design.b, design.a, worN=points, fs=design.fs)
    magnitude_db = 20 * np.log10(np.maximum(np.abs(response), 1e-12))
    phase = np.unwrap(np.angle(response))
    return frequencies, magnitude_db, phase


def filter_signal(design: FilterDesign, samples: np.ndarray) -> np.ndarray:
    samples = np.asarray(samples, dtype=float)
    if samples.size > 50_000:
        raise ValueError("演示信号过长。")
    return signal.lfilter(design.b, design.a, samples)


def make_test_signal(
    *,
    fs: float = 1000.0,
    duration: float = 0.2,
    low_freq: float = 20.0,
    high_freq: float = 180.0,
) -> tuple[np.ndarray, np.ndarray]:
    nyquist = fs / 2
    if not (0 < low_freq < nyquist and 0 < high_freq < nyquist):
        raise ValueError("测试信号频率必须低于奈奎斯特频率。")
    n = int(fs * duration)
    t = np.arange(n) / fs
    samples = np.sin(2 * np.pi * low_freq * t) + 0.6 * np.sin(2 * np.pi * high_freq * t)
    return t, samples


def filter_demo(
    design: FilterDesign,
    *,
    low_freq: float = 20.0,
    high_freq: float = 180.0,
    duration: float = 0.2,
) -> FilterDemo:
    t, original = make_test_signal(
        fs=design.fs, duration=duration, low_freq=low_freq, high_freq=high_freq
    )
    filtered = filter_signal(design, original)
    frequencies, magnitude_db, phase = frequency_response(design)
    return FilterDemo(
        design=design,
        time=t,
        original=original,
        filtered=filtered,
        frequencies=frequencies,
        magnitude_db=magnitude_db,
        phase_rad=phase,
    )
