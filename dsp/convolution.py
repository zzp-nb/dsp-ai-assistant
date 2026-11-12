"""Discrete linear convolution and a step-by-step calculation table."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ConvolutionResult:
    x: np.ndarray
    h: np.ndarray
    y: np.ndarray
    n_x: np.ndarray
    n_h: np.ndarray
    n_y: np.ndarray
    steps: list[dict] = field(default_factory=list)


def parse_sequence(text: str, *, max_length: int = 20) -> np.ndarray:
    cleaned = (text or "").replace("，", ",").replace("；", ",").replace(";", ",")
    values = [part.strip() for part in re.split(r"[,\s]+", cleaned) if part.strip()]
    if not values:
        raise ValueError("序列不能为空，请用逗号分隔数值。")
    if len(values) > max_length:
        raise ValueError(f"序列长度不能超过 {max_length}。")
    try:
        array = np.asarray([float(value) for value in values], dtype=float)
    except ValueError as exc:
        raise ValueError("序列中包含无法识别的数值，请只输入数字。") from exc
    if not np.all(np.isfinite(array)):
        raise ValueError("序列中不能包含 NaN 或无穷大。")
    return array


def convolution_steps(x: np.ndarray, h: np.ndarray) -> list[dict]:
    x = np.asarray(x, dtype=float).ravel()
    h = np.asarray(h, dtype=float).ravel()
    y = np.convolve(x, h, mode="full")
    steps: list[dict] = []
    for n in range(y.size):
        terms = []
        for k in range(x.size):
            h_index = n - k
            if 0 <= h_index < h.size:
                terms.append((int(k), int(h_index), float(x[k]), float(h[h_index])))
        steps.append(
            {
                "n": n,
                "terms": terms,
                "value": float(y[n]),
                "expression": " + ".join(
                    f"x[{k}]·h[{j}]={xk:g}×{hj:g}" for k, j, xk, hj in terms
                ),
            }
        )
    return steps


def linear_convolution(x: np.ndarray | list[float], h: np.ndarray | list[float]) -> ConvolutionResult:
    x_array = np.asarray(x, dtype=float).ravel()
    h_array = np.asarray(h, dtype=float).ravel()
    if x_array.size == 0 or h_array.size == 0:
        raise ValueError("卷积序列不能为空。")
    if x_array.size > 20 or h_array.size > 20:
        raise ValueError("演示用序列长度不能超过 20。")
    y = np.convolve(x_array, h_array, mode="full")
    return ConvolutionResult(
        x=x_array,
        h=h_array,
        y=y,
        n_x=np.arange(x_array.size),
        n_h=np.arange(h_array.size),
        n_y=np.arange(y.size),
        steps=convolution_steps(x_array, h_array),
    )
