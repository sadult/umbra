"""DSP chain: 10-band parametric EQ, bass enhancer, stereo tools, soft limiter."""
import math

import numpy as np

try:
    from scipy.signal import sosfilt
except Exception:  # pragma: no cover
    sosfilt = None

EQ_FREQS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
EQ_LABELS = ["31", "62", "125", "250", "500", "1K", "2K", "4K", "8K", "16K"]

EQ_PRESETS = {
    "Flat":        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "Bass Boost":  [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
    "Deep Bass":   [8, 6, 3, 0, -1, 0, 0, 0, 1, 1],
    "Treble":      [0, 0, 0, 0, 0, 1, 2, 4, 5, 6],
    "Vocal":       [-2, -2, -1, 1, 3, 4, 3, 1, 0, -1],
    "Rock":        [4, 3, 2, 0, -1, -1, 1, 3, 4, 4],
    "Electronic":  [5, 4, 1, 0, -2, 1, 0, 2, 4, 5],
    "Hip-Hop":     [5, 4, 2, 3, -1, -1, 1, 0, 2, 3],
    "Jazz":        [3, 2, 1, 2, -1, -1, 0, 1, 2, 3],
    "Classical":   [4, 3, 2, 1, -1, -1, 0, 2, 3, 4],
    "Acoustic":    [4, 3, 2, 1, 1, 1, 2, 3, 2, 1],
    "Loudness":    [6, 4, 0, 0, -2, 0, -1, -2, 4, 2],
    "Late Night":  [3, 2, 1, 0, 0, 0, -1, -2, -3, -4],
    "Headphones":  [3, 2, 0, -1, -1, 0, 1, 2, 3, 2],
}


def _biquad(kind: str, f0: float, sr: int, gain_db: float = 0.0, q: float = 0.707):
    """RBJ cookbook biquad → second-order section [b0 b1 b2 a0 a1 a2] (normalised)."""
    f0 = min(f0, sr * 0.45)
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * f0 / sr
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2 * q)
    if kind == "peak":
        b0, b1, b2 = 1 + alpha * A, -2 * cw, 1 - alpha * A
        a0, a1, a2 = 1 + alpha / A, -2 * cw, 1 - alpha / A
    elif kind == "lowshelf":
        sa = 2 * math.sqrt(A) * alpha
        b0 = A * ((A + 1) - (A - 1) * cw + sa)
        b1 = 2 * A * ((A - 1) - (A + 1) * cw)
        b2 = A * ((A + 1) - (A - 1) * cw - sa)
        a0 = (A + 1) + (A - 1) * cw + sa
        a1 = -2 * ((A - 1) + (A + 1) * cw)
        a2 = (A + 1) + (A - 1) * cw - sa
    elif kind == "highshelf":
        sa = 2 * math.sqrt(A) * alpha
        b0 = A * ((A + 1) + (A - 1) * cw + sa)
        b1 = -2 * A * ((A - 1) + (A + 1) * cw)
        b2 = A * ((A + 1) + (A - 1) * cw - sa)
        a0 = (A + 1) - (A - 1) * cw + sa
        a1 = 2 * ((A - 1) - (A + 1) * cw)
        a2 = (A + 1) - (A - 1) * cw - sa
    elif kind == "highpass":
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    else:
        raise ValueError(kind)
    return [b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]


def eq_response(gains, preamp=0.0, bass=0.0, sr=48000, points=200):
    """Magnitude response in dB for drawing the EQ curve."""
    freqs = np.geomspace(20, 20000, points)
    sos = build_sos(gains, bass, sr)
    w = 2 * np.pi * freqs / sr
    z = np.exp(1j * w)
    h = np.ones_like(z)
    for b0, b1, b2, _a0, a1, a2 in sos:
        h *= (b0 + b1 / z + b2 / z ** 2) / (1 + a1 / z + a2 / z ** 2)
    return freqs, 20 * np.log10(np.abs(h) + 1e-9) + preamp


def build_sos(gains, bass, sr):
    sos = []
    for i, (f, g) in enumerate(zip(EQ_FREQS, gains)):
        if abs(g) < 0.05:
            continue
        if i == 0:
            sos.append(_biquad("lowshelf", f * 1.4, sr, g, 0.7))
        elif i == len(EQ_FREQS) - 1:
            sos.append(_biquad("highshelf", f * 0.75, sr, g, 0.7))
        else:
            sos.append(_biquad("peak", f, sr, g, 1.1))
    if bass > 0.05:
        sos.append(_biquad("lowshelf", 90, sr, bass, 0.6))
    return sos


class DSPChain:
    def __init__(self, s):
        self.s = s
        self._sr = None
        self._sos = None
        self._zi = None
        self._dirty = True
        s.changed.connect(self._on_setting)

    def _on_setting(self, key, _v):
        if key.startswith("eq_") or key == "bass_boost":
            self._dirty = True

    def _rebuild(self, sr):
        self._sr = sr
        self._dirty = False
        if not self.s["eq_enabled"] or sosfilt is None:
            self._sos = None
            return
        sos = build_sos(self.s["eq_gains"], self.s["bass_boost"], sr)
        if not sos:
            self._sos = None
            return
        self._sos = np.array(sos, dtype=np.float64)
        self._zi = np.zeros((len(sos), 2, 2))

    def reset(self):
        if self._sos is not None:
            self._zi = np.zeros((len(self._sos), 2, 2))

    def process(self, x: np.ndarray, sr: int) -> np.ndarray:
        if len(x) == 0:
            return x
        if self._dirty or sr != self._sr:
            self._rebuild(sr)
        s = self.s
        if s["eq_enabled"]:
            pre = s["eq_preamp"]
            if abs(pre) > 0.01:
                x = x * (10 ** (pre / 20))
            if self._sos is not None:
                x, self._zi = sosfilt(self._sos, x, axis=0, zi=self._zi)
                x = x.astype(np.float32, copy=False)
        if s["swap_channels"]:
            x = x[:, ::-1]
        width = s["stereo_width"]
        if s["mono"]:
            m = x.mean(axis=1, keepdims=True)
            x = np.repeat(m, 2, axis=1)
        elif abs(width - 1.0) > 0.01:
            mid = (x[:, 0] + x[:, 1]) * 0.5
            side = (x[:, 0] - x[:, 1]) * 0.5 * width
            x = np.stack([mid + side, mid - side], axis=1)
        bal = s["balance"]
        if abs(bal) > 0.01:
            x = x * np.array([min(1.0, 1 - bal), min(1.0, 1 + bal)], dtype=np.float32)
        if s["limiter"]:
            a = np.abs(x)
            if a.max(initial=0) > 0.89:
                t = 0.89
                over = a > t
                x = np.where(over, np.sign(x) * (t + (1 - t) * np.tanh((a - t) / (1 - t))), x)
        return np.ascontiguousarray(x, dtype=np.float32)


class LinearResampler:
    """Tiny stateful resampler used only when the device refuses the native rate."""

    def __init__(self, src_sr, dst_sr):
        self.ratio = src_sr / dst_sr
        self.pos = 0.0
        self.last = np.zeros((1, 2), np.float32)

    def process(self, x):
        if len(x) == 0:
            return x
        buf = np.concatenate([self.last, x])
        n_out = int((len(buf) - 1 - self.pos) / self.ratio)
        if n_out <= 0:
            return np.zeros((0, 2), np.float32)
        idx = self.pos + np.arange(n_out) * self.ratio
        i0 = idx.astype(np.int64)
        frac = (idx - i0)[:, None].astype(np.float32)
        out = buf[i0] * (1 - frac) + buf[i0 + 1] * frac
        self.pos = idx[-1] + self.ratio - (len(buf) - 1)
        self.last = buf[-1:]
        return out.astype(np.float32)
