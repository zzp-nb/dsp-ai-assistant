"""Interactive DSP signal lab."""

from __future__ import annotations

import streamlit as st

from dsp.convolution import linear_convolution, parse_sequence
from dsp.fft import compute_spectrum, make_multitone
from dsp.filters import design_fir, design_iir, filter_demo
from dsp.sampling import sampling_demo
from ui.guard import render_shell, setup_page
from ui.plots import (
    convolution_figure,
    filter_figure,
    sampling_figure,
    spectrum_figure,
)
from ui.theme import footer, note, page_header

import matplotlib.pyplot as plt


setup_page("信号仿真")
render_shell()
page_header(
    "SIGNAL LAB",
    "信号仿真",
    "改变参数，观察结果。所有图都由 NumPy / SciPy 实时计算，不是预置图片；下方解释会跟随参数变化。",
)

st.markdown(
    '<div class="dsp-note">实验建议：先固定信号频率，逐步降低采样频率，找到波形“看起来变慢”的临界点，'
    "再对照奈奎斯特频率解释混叠。</div>",
    unsafe_allow_html=True,
)
st.write("")

tab_sampling, tab_conv, tab_fft, tab_fir, tab_iir = st.tabs(
    ["采样与混叠", "离散卷积", "DFT / FFT 频谱", "FIR 滤波器", "IIR 滤波器"]
)

with tab_sampling:
    st.markdown("#### 连续信号采样与理想重建")
    with st.form("sampling_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            f_signal = st.slider("信号频率 f (Hz)", 0.5, 60.0, 5.0, 0.5)
        with col2:
            fs = st.slider("采样频率 fs (Hz)", 2.0, 200.0, 40.0, 1.0)
        with col3:
            duration = st.slider("观察时长 (s)", 0.05, 1.0, 0.4, 0.05)
        start = st.form_submit_button("开始采样仿真", type="primary")
    if start:
        try:
            st.session_state["sampling_result"] = sampling_demo(
                f_signal=f_signal, fs=fs, duration=duration
            )
        except ValueError as exc:
            st.error(str(exc))
    result = st.session_state.get("sampling_result")
    if result is not None:
        metrics = st.columns(4)
        metrics[0].metric("奈奎斯特频率", f"{result.nyquist:g} Hz")
        metrics[1].metric("每周期采样点", f"{result.fs / result.f_signal:.2f}")
        metrics[2].metric("采样点数", result.sample_count)
        metrics[3].metric("观测频率", f"{result.alias_frequency:g} Hz")
        fig = sampling_figure(result)
        st.pyplot(fig, width="stretch")
        plt.close(fig)
        if result.aliased:
            st.error(
                f"发生混叠：信号 {result.f_signal:g} Hz 高于奈奎斯特频率 {result.nyquist:g} Hz。"
                f"采样后会被误认为约 {result.alias_frequency:g} Hz 的低频信号。"
            )
            st.markdown(
                "**关键参数说明**：采样间隔 $T_s=1/f_s$。当 $f_s<2f$ 时，采样序列无法唯一恢复原信号。"
                "图中虚线是用理想 sinc 插值从采样点得到的重建结果，它与原信号不再重合。"
            )
        else:
            st.success(
                f"满足采样定理：$f_s={result.fs:g}$ Hz > $2f={2 * result.f_signal:g}$ Hz，"
                "采样点保留了原信号信息。"
            )
            st.markdown(
                "**关键参数说明**：增加 $f_s$ 会让采样点更密，理想重建更接近连续曲线。"
                "实际系统还需要抗混叠低通滤波器，不能只靠提高采样率解决带外噪声。"
            )
    else:
        st.caption("点击“开始采样仿真”后显示波形。")

with tab_conv:
    st.markdown("#### 离散线性卷积 $y[n]=x[n]*h[n]$")
    with st.form("conv_form"):
        col1, col2 = st.columns(2)
        with col1:
            x_text = st.text_input("输入序列 x[n]", value="1, 2, 3")
        with col2:
            h_text = st.text_input("单位脉冲响应 h[n]", value="1, 1, 1")
        start_conv = st.form_submit_button("计算并绘制卷积", type="primary")
    if start_conv:
        try:
            x = parse_sequence(x_text)
            h = parse_sequence(h_text)
            st.session_state["conv_result"] = linear_convolution(x, h)
        except ValueError as exc:
            st.error(str(exc))
    conv = st.session_state.get("conv_result")
    if conv is not None:
        st.caption(f"x[n] 长度 {conv.x.size}，h[n] 长度 {conv.h.size}，输出长度 $N_x+N_h-1={conv.y.size}$。")
        fig = convolution_figure(conv)
        st.pyplot(fig, width="stretch")
        plt.close(fig)
        with st.expander("查看逐步计算表", expanded=True):
            rows = []
            for step in conv.steps[:14]:
                rows.append(
                    {
                        "n": step["n"],
                        "y[n] = Σ x[k]h[n-k]": step["expression"],
                        "结果": f"{step['value']:g}",
                    }
                )
            st.dataframe(rows, width="stretch", hide_index=True)
            if len(conv.steps) > 14:
                st.caption("仅显示前 14 个输出样本。")
        st.markdown(
            "**要点**：卷积是“翻转—平移—相乘—求和”。有限长序列卷积的结果长度为 "
            "$N_x+N_h-1$；计算时注意 $h[n-k]$ 的下标范围，避免把线性卷积与循环卷积混淆。"
        )
    else:
        st.caption("输入两个有限长序列，观察卷积结果与逐点计算过程。")

with tab_fft:
    st.markdown("#### 时域波形与单边幅度谱")
    with st.form("fft_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            f1 = st.slider("频率分量 1 (Hz)", 10.0, 300.0, 50.0, 5.0, key="fft_f1")
            a1 = st.slider("幅度 1", 0.1, 2.0, 1.0, 0.1, key="fft_a1")
        with col2:
            use_second = st.checkbox("加入第二个频率分量", value=True)
            f2 = st.slider("频率分量 2 (Hz)", 10.0, 400.0, 120.0, 5.0, key="fft_f2")
        with col3:
            fs_fft = st.select_slider("采样频率 (Hz)", options=[500.0, 800.0, 1000.0, 2000.0], value=1000.0)
            duration_fft = st.slider("时长 (s)", 0.1, 1.0, 0.5, 0.05, key="fft_duration")
            window = st.selectbox("窗函数", ["hann", "hamming", "blackman", "rectangular"])
        start_fft = st.form_submit_button("分析频谱", type="primary")
    if start_fft:
        try:
            freqs = [f1, f2] if use_second else [f1]
            amps = [a1, 0.6] if use_second else [a1]
            _, signal = make_multitone(freqs, amps, fs=fs_fft, duration=duration_fft)
            st.session_state["fft_result"] = compute_spectrum(signal, fs_fft, window=window)
            st.session_state["fft_params"] = {"freqs": freqs, "fs": fs_fft, "window": window}
        except ValueError as exc:
            st.error(str(exc))
    spectrum = st.session_state.get("fft_result")
    if spectrum is not None:
        params = st.session_state.get("fft_params", {})
        st.caption(
            f"N={spectrum.n}，频率分辨率 $\\Delta f=f_s/N={spectrum.resolution:.3f}$ Hz，"
            f"窗函数：{params.get('window', '')}"
        )
        fig = spectrum_figure(spectrum)
        st.pyplot(fig, width="stretch")
        plt.close(fig)
        if spectrum.peaks:
            st.markdown("**检测到的主要峰值：**")
            peak_cols = st.columns(min(4, len(spectrum.peaks)))
            for index, peak in enumerate(spectrum.peaks):
                peak_cols[index].metric(
                    f"峰 {index + 1}", f"{peak['frequency']:.1f} Hz", f"{peak['amplitude']:.2f}"
                )
        st.markdown(
            "**如何读图**：峰值位置对应信号频率，峰值高度与幅度和窗函数有关。"
            "频率分辨率由 $f_s/N$ 决定；补零只能让频谱曲线更平滑，不能真正提高分辨率。"
            "非整周期截断会产生频谱泄漏。"
        )
    else:
        st.caption("设置频率分量和采样参数，点击“分析频谱”。")

with tab_fir:
    st.markdown("#### FIR 滤波器：时域与频率响应")
    with st.form("fir_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            fir_type = st.selectbox("类型", ["lowpass", "highpass"], key="fir_type")
            fir_cutoff = st.slider("截止频率 (Hz)", 10.0, 400.0, 100.0, 5.0)
        with col2:
            fir_taps = st.slider("抽头数（奇数更常用）", 11, 201, 51, 2)
            fir_window = st.selectbox("窗函数", ["hamming", "hann", "blackman"], key="fir_window")
        with col3:
            fir_fs = st.select_slider("采样频率 (Hz)", options=[500.0, 1000.0, 2000.0], value=1000.0)
            test_low = st.slider("测试低频 (Hz)", 5.0, 100.0, 20.0, 5.0, key="fir_low")
            test_high = st.slider("测试高频 (Hz)", 100.0, 450.0, 180.0, 5.0, key="fir_high")
        start_fir = st.form_submit_button("设计并测试 FIR", type="primary")
    if start_fir:
        try:
            design = design_fir(
                filter_type=fir_type,
                cutoff=fir_cutoff,
                fs=fir_fs,
                num_taps=fir_taps,
                window=fir_window,
            )
            st.session_state["fir_result"] = filter_demo(
                design, low_freq=test_low, high_freq=test_high
            )
        except ValueError as exc:
            st.error(str(exc))
    fir = st.session_state.get("fir_result")
    if fir is not None:
        st.caption(
            f"{fir.design.coefficients_label}；阶数 {fir.design.order}；"
            f"群延迟约 {(fir.design.b.size - 1) / 2 / fir.design.fs * 1000:.2f} ms。"
        )
        fig = filter_figure(fir)
        st.pyplot(fig, width="stretch")
        plt.close(fig)
        st.markdown(
            "**观察要点**：抽头数越多，过渡带通常越窄，但群延迟增大、计算量增加。"
            "`firwin` 设计的是线性相位 FIR（系数对称），通带内相位为线性；"
            "截止频率是 -6 dB 附近的近似位置，不是理想的砖墙。"
        )
    else:
        st.caption("设置截止频率与抽头数，观察低通/高通效果。")

with tab_iir:
    st.markdown("#### IIR 滤波器：低阶实现与相位非线性")
    with st.form("iir_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            iir_type = st.selectbox("类型", ["lowpass", "highpass"], key="iir_type")
            iir_cutoff = st.slider("截止频率 (Hz)", 10.0, 400.0, 100.0, 5.0)
        with col2:
            iir_family = st.selectbox("设计方法", ["butter", "cheby1"], key="iir_family")
            iir_order = st.slider("阶数", 1, 8, 4)
        with col3:
            iir_fs = st.select_slider("采样频率 (Hz)", options=[500.0, 1000.0, 2000.0], value=1000.0)
            iir_low = st.slider("测试低频 (Hz)", 5.0, 100.0, 20.0, 5.0, key="iir_low")
            iir_high = st.slider("测试高频 (Hz)", 100.0, 450.0, 180.0, 5.0, key="iir_high")
        start_iir = st.form_submit_button("设计并测试 IIR", type="primary")
    if start_iir:
        try:
            design = design_iir(
                filter_type=iir_type,
                cutoff=iir_cutoff,
                fs=iir_fs,
                order=iir_order,
                family=iir_family,
            )
            st.session_state["iir_result"] = filter_demo(
                design, low_freq=iir_low, high_freq=iir_high
            )
        except ValueError as exc:
            st.error(str(exc))
    iir = st.session_state.get("iir_result")
    if iir is not None:
        st.caption(f"{iir.design.coefficients_label}；$b$ 系数 {len(iir.design.b)} 个，$a$ 系数 {len(iir.design.a)} 个。")
        fig = filter_figure(iir)
        st.pyplot(fig, width="stretch")
        plt.close(fig)
        st.markdown(
            "**观察要点**：相同阶数下 IIR 通常比 FIR 更省计算量、过渡带更陡，"
            "但相位非线性，且反馈结构对系数量化更敏感。阶数过高时可能不稳定，"
            "实际设计要检查极点是否都在单位圆内。"
        )
    else:
        st.caption("选择 Butterworth 或 Chebyshev I 设计，观察幅频与相频响应。")

st.divider()
note(
    "仿真用于建立直觉，不能替代完整实验报告。图中使用理想采样与理想重建；"
    "真实 ADC/DAC、量化噪声、滤波器实现误差未全部建模。",
    warning=True,
)
footer()
