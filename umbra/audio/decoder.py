"""Streaming decoders: libsndfile first, FFmpeg pipe as universal fallback."""
import shutil
import subprocess
import sys

import numpy as np

try:
    import soundfile as sf
except Exception:  # pragma: no cover
    sf = None

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
_NOWIN = 0x08000000 if sys.platform == "win32" else 0

SF_EXTS = {".wav", ".flac", ".ogg", ".oga", ".aif", ".aiff", ".mp3", ".opus"}


class DecodeError(Exception):
    pass


class BaseDecoder:
    samplerate = 44100
    channels = 2
    duration = 0.0
    subtype = ""
    gain = 1.0          # linear pre-gain (ReplayGain / leveling)

    def read(self, frames: int) -> np.ndarray:
        raise NotImplementedError

    def seek(self, seconds: float):
        raise NotImplementedError

    def close(self):
        pass


def _to_stereo(a: np.ndarray) -> np.ndarray:
    if a.ndim == 1:
        a = a[:, None]
    if a.shape[1] == 1:
        return np.repeat(a, 2, axis=1)
    if a.shape[1] > 2:
        return np.ascontiguousarray(a[:, :2])
    return a


class SoundFileDecoder(BaseDecoder):
    def __init__(self, path: str):
        if sf is None:
            raise DecodeError("soundfile unavailable")
        try:
            self.f = sf.SoundFile(path)
        except Exception as e:
            raise DecodeError(str(e))
        self.samplerate = self.f.samplerate
        self.channels = self.f.channels
        self.duration = self.f.frames / float(self.samplerate) if self.f.frames > 0 else 0.0
        self.subtype = self.f.subtype

    def read(self, frames):
        a = self.f.read(frames, dtype="float32", always_2d=True)
        return _to_stereo(a)

    def seek(self, seconds):
        try:
            self.f.seek(int(max(0.0, seconds) * self.samplerate))
        except Exception:
            pass

    def close(self):
        try:
            self.f.close()
        except Exception:
            pass


def ffprobe_duration(src: str) -> float:
    if not FFPROBE:
        return 0.0
    try:
        out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", src], capture_output=True, text=True,
                             timeout=15, creationflags=_NOWIN).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


class FFmpegDecoder(BaseDecoder):
    def __init__(self, src: str, samplerate: int = 48000, duration: float = 0.0, headers: dict | None = None):
        if not FFMPEG:
            raise DecodeError("FFmpeg not found on PATH — needed for this format / streaming")
        self.src = src
        self.samplerate = samplerate
        self.headers = headers or {}
        self.duration = duration or (ffprobe_duration(src) if not src.startswith("http") else 0.0)
        self.subtype = "FFMPEG"
        self.proc = None
        self._start(0.0)

    def _start(self, pos):
        self.close()
        cmd = [FFMPEG, "-nostdin", "-loglevel", "error"]
        if self.headers:
            cmd += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())]
        if self.src.startswith("http"):
            cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "4"]
        if pos > 0:
            cmd += ["-ss", f"{pos:.3f}"]
        cmd += ["-i", self.src, "-vn", "-f", "f32le", "-ac", "2", "-ar", str(self.samplerate), "pipe:1"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     stdin=subprocess.DEVNULL, creationflags=_NOWIN, bufsize=1 << 16)

    def read(self, frames):
        if not self.proc:
            return np.zeros((0, 2), np.float32)
        data = self.proc.stdout.read(frames * 8)
        n = len(data) // 8
        if n == 0:
            return np.zeros((0, 2), np.float32)
        return np.frombuffer(data[: n * 8], dtype=np.float32).reshape(-1, 2).copy()

    def seek(self, seconds):
        self._start(max(0.0, seconds))

    def close(self):
        if self.proc:
            try:
                self.proc.kill()
                self.proc.wait(timeout=1)
            except Exception:
                pass
            self.proc = None


def open_decoder(path: str, duration_hint: float = 0.0, headers=None, force_rate: int | None = None) -> BaseDecoder:
    """Open the best decoder for a local path or a resolved http URL."""
    if path.startswith("http"):
        return FFmpegDecoder(path, force_rate or 48000, duration_hint, headers)
    ext = path[path.rfind("."):].lower() if "." in path else ""
    if ext in SF_EXTS and sf is not None and not force_rate:
        try:
            return SoundFileDecoder(path)
        except DecodeError:
            pass
    return FFmpegDecoder(path, force_rate or 48000, duration_hint)
