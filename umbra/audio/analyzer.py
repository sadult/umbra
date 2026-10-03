"""Real-time analysis: FFT spectrum, VU levels, EBU R128 loudness, peak and DR."""
import math
import threading

import numpy as np

from .dsp import _biquad

try:
    from scipy.signal import sosfilt
except Exception:  # pragma: no cover
    sosfilt = None


class Ring:
    def __init__(self, size=8192):
        self.buf = np.zeros((size, 2), np.float32)
        self.size = size
        self.w = 0
        self.lock = threading.Lock()

    def push(self, x):
        n = len(x)
        if n == 0:
            return
        if n >= self.size:
            x = x[-self.size:]
            n = self.size
        with self.lock:
            end = self.w + n
            if end <= self.size:
                self.buf[self.w:end] = x
            else:
                k = self.size - self.w
                self.buf[self.w:] = x[:k]
                self.buf[: n - k] = x[k:]
            self.w = end % self.size

    def latest(self, n):
        with self.lock:
            idx = (np.arange(self.w - n, self.w)) % self.size
            return self.buf[idx].copy()

    def clear(self):
        with self.lock:
            self.buf[:] = 0


class Spectrum:
    def __init__(self, ring: Ring):
        self.ring = ring
        self.sr = 44100
        self.n = 4096
        self.win = np.hanning(self.n).astype(np.float32)
        self._maps = {}

    def _bands(self, nb):
        key = (self.sr, nb)
        if key not in self._maps:
            nyq = self.sr / 2
            edges = np.geomspace(20, min(20000, nyq * 0.98), nb + 1)
            binw = self.sr / self.n
            lo = np.clip((edges[:-1] / binw).astype(int), 1, self.n // 2 - 1)
            hi = np.clip((edges[1:] / binw).astype(int), 1, self.n // 2)
            hi = np.maximum(hi, lo + 1)
            # gentle tilt so highs are visible (pink-noise compensation, +3 dB/oct)
            centers = np.sqrt(edges[:-1] * edges[1:])
            tilt = 4.5 * np.log2(centers / 1000.0)
            self._maps[key] = (lo, hi, tilt.astype(np.float32))
        return self._maps[key]

    def compute(self, nb=56):
        x = self.ring.latest(self.n).mean(axis=1) * self.win
        mag = np.abs(np.fft.rfft(x)) / (self.n / 4)
        lo, hi, tilt = self._bands(nb)
        cs = np.concatenate([[0.0], np.cumsum(mag ** 2)])
        pw = (cs[hi] - cs[lo]) / (hi - lo)
        db = 10 * np.log10(pw + 1e-12) + tilt
        return np.clip((db + 72) / 66, 0, 1).astype(np.float32)

    def waveform(self, n=512):
        return self.ring.latest(n)

    def levels(self):
        x = self.ring.latest(2048)
        rms = np.sqrt(np.mean(x ** 2, axis=0) + 1e-12)
        peak = np.abs(x).max(axis=0)
        return 20 * np.log10(rms), 20 * np.log10(peak + 1e-9)


class LoudnessMeter:
    """ITU-R BS.1770 / EBU R128 loudness (momentary, short-term, integrated) + sample peak + DR."""

    def __init__(self):
        self.reset(44100)

    def reset(self, sr):
        self.sr = sr
        if sosfilt is not None:
            self.sos = np.array([_biquad("highshelf", 1681.97, sr, 4.0, 0.7071),
                                 _biquad("highpass", 38.135, sr, 0, 0.5003)])
            self.zi = np.zeros((2, 2, 2))
        else:
            self.sos = None
        self.sub = int(sr * 0.1)
        self.acc = np.zeros(0, np.float64)
        self.ms100 = []
        self.blocks = []
        self.peak = 0.0
        self.dr_win = int(sr * 3)
        self.dr_acc = np.zeros((0, 2), np.float32)
        self.dr_rms = []
        self.dr_peak = []
        self.momentary = -70.0
        self.short = -70.0
        self.valid = True
        self.lock = threading.Lock()

    def invalidate(self):
        self.valid = False

    def push(self, x: np.ndarray):
        if self.sos is None or len(x) == 0:
            return
        with self.lock:
            self.peak = max(self.peak, float(np.abs(x).max()))
            y, self.zi = sosfilt(self.sos, x, axis=0, zi=self.zi)
            e = (y ** 2).sum(axis=1)
            self.acc = np.concatenate([self.acc, e])
            while len(self.acc) >= self.sub:
                self.ms100.append(float(self.acc[: self.sub].mean()))
                self.acc = self.acc[self.sub:]
                if len(self.ms100) >= 4:
                    z = sum(self.ms100[-4:]) / 4
                    l = -0.691 + 10 * math.log10(z + 1e-12)
                    self.momentary = l
                    self.blocks.append(z)
                if len(self.ms100) >= 30:
                    z = sum(self.ms100[-30:]) / 30
                    self.short = -0.691 + 10 * math.log10(z + 1e-12)
                if len(self.ms100) > 40:
                    self.ms100 = self.ms100[-40:]
            # DR meter (TT DR approximation)
            self.dr_acc = np.concatenate([self.dr_acc, x])
            while len(self.dr_acc) >= self.dr_win:
                c = self.dr_acc[: self.dr_win]
                self.dr_acc = self.dr_acc[self.dr_win:]
                self.dr_rms.append(np.sqrt(2 * np.mean(c.astype(np.float64) ** 2, axis=0)))
                self.dr_peak.append(np.abs(c).max(axis=0))

    def integrated(self):
        with self.lock:
            b = np.array(self.blocks)
        if len(b) == 0:
            return None
        l = -0.691 + 10 * np.log10(b + 1e-12)
        b = b[l > -70]
        if len(b) == 0:
            return None
        rel = -0.691 + 10 * math.log10(b.mean()) - 10
        l = -0.691 + 10 * np.log10(b + 1e-12)
        g = b[l > rel]
        if len(g) == 0:
            return None
        return -0.691 + 10 * math.log10(g.mean())

    def peak_db(self):
        return 20 * math.log10(self.peak) if self.peak > 0 else None

    def dr(self):
        with self.lock:
            if len(self.dr_rms) < 2:
                return None
            r = np.array(self.dr_rms)
            p = np.array(self.dr_peak)
        vals = []
        for ch in range(r.shape[1]):
            rs = np.sort(r[:, ch])[::-1]
            top = rs[: max(1, int(round(len(rs) * 0.2)))]
            rr = math.sqrt(float(np.mean(top ** 2)))
            ps = np.sort(p[:, ch])[::-1]
            pk = float(ps[1] if len(ps) > 1 else ps[0])
            if rr > 0 and pk > 0:
                vals.append(20 * math.log10(pk / rr))
        return float(np.mean(vals)) if vals else None
