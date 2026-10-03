"""Umbra audio engine — threaded producer, PortAudio output, gapless & crossfade."""
import collections
import queue
import threading
import time
import traceback

import numpy as np
from PySide6.QtCore import QObject, Signal

from .analyzer import LoudnessMeter, Ring, Spectrum
from .decoder import DecodeError, open_decoder
from .dsp import DSPChain, LinearResampler

try:
    import sounddevice as sd
except Exception as _e:  # PortAudio missing
    sd = None
    SD_ERROR = str(_e)
else:
    SD_ERROR = ""

BLOCK = 2048
MAX_CHUNKS = 5


class AudioEngine(QObject):
    stateChanged = Signal(str)            # playing | paused | stopped | buffering
    trackStarted = Signal(object)         # src dict that just became audible
    trackEnded = Signal(object)           # src finished and nothing follows
    analysisDone = Signal(object, object)  # src, dict(lufs, peak, dr)
    error = Signal(str)
    formatChanged = Signal(object)        # dict describing current stream

    def __init__(self, settings, resolver=None):
        super().__init__()
        self.s = settings
        self.resolver = resolver          # callable(src) -> (url, headers) for streaming sources
        self.dsp = DSPChain(settings)
        self.ring = Ring(8192)
        self.spectrum = Spectrum(self.ring)
        self.loud = LoudnessMeter()
        self.next_provider = None         # callable() -> src | None (peek, no side effects)
        self.gain_for = lambda src: 1.0   # leveling callback

        self._lock = threading.RLock()
        self._chunks = collections.deque()
        self._gen = 0
        self._cmd = queue.Queue()
        self._stream = None
        self._stream_sr = None
        self._resampler = None
        self._dec = None
        self._src = None
        self._next = None                 # (decoder, src) during crossfade
        self._xf_total = 0
        self._xf_pos = 0
        self._left = None
        self._left_gen = -1
        self._playing_src = None
        self._played = 0
        self._paused = True
        self._gain = 0.0
        self._state = "stopped"
        self.volume = settings["volume"]
        self.muted = settings["muted"]
        self.format = {}
        self._thread = threading.Thread(target=self._producer, name="umbra-audio", daemon=True)
        self._thread.start()

    # ───────────────────────────── public API (GUI thread)
    @property
    def state(self):
        return self._state

    def available(self):
        return sd is not None

    def load(self, src, start=0.0, autoplay=True):
        self._cmd.put(("load", src, start, autoplay))

    def seek(self, seconds):
        self._cmd.put(("seek", seconds))

    def play(self):
        if self._src is None:
            return
        self._paused = False
        self._set_state("playing")

    def pause(self):
        self._paused = True
        self._set_state("paused")

    def toggle(self):
        if self._paused:
            self.play()
        else:
            self.pause()

    def stop(self):
        self._cmd.put(("stop",))

    def set_volume(self, v):
        self.volume = max(0.0, min(1.0, v))

    def position(self):
        sr = self._stream_sr or 44100
        if self._resampler is not None and self._dec is not None:
            sr = self._stream_sr
        return self._played / float(sr) if sr else 0.0

    def duration(self):
        d = self._dec
        if self._playing_src and self._playing_src.get("duration"):
            if d is None or not d.duration:
                return float(self._playing_src["duration"])
        return d.duration if d is not None and d.duration else float((self._playing_src or {}).get("duration") or 0)

    def devices(self):
        if sd is None:
            return []
        out = []
        try:
            apis = sd.query_hostapis()
            for i, d in enumerate(sd.query_devices()):
                if d["max_output_channels"] > 0:
                    out.append((i, f"{d['name']}  ·  {apis[d['hostapi']]['name']}"))
        except Exception:
            pass
        return out

    def restart_output(self):
        self._cmd.put(("reopen",))

    def shutdown(self):
        self._cmd.put(("quit",))
        try:
            if self._stream:
                self._stream.close()
        except Exception:
            pass

    # ───────────────────────────── internals
    def _set_state(self, st):
        if st != self._state:
            self._state = st
            self.stateChanged.emit(st)

    def _open_stream(self, sr):
        if sd is None:
            raise RuntimeError("PortAudio / sounddevice not available: " + SD_ERROR)
        if self._stream is not None and self._stream_sr == sr:
            return sr
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        dev = self.s["output_device"]
        lat = max(0.03, self.s["buffer_ms"] / 1000.0)
        extra = None
        if self.s["exclusive"]:
            try:
                extra = sd.WasapiSettings(exclusive=True)
            except Exception:
                extra = None
        tries = [(sr, extra), (sr, None)]
        try:
            dflt = int(sd.query_devices(dev if dev is not None else sd.default.device[1])["default_samplerate"])
            tries.append((dflt, None))
        except Exception:
            pass
        last = None
        for rate, ex in tries:
            try:
                st = sd.OutputStream(samplerate=rate, channels=2, dtype="float32", device=dev,
                                     latency=lat, callback=self._callback, extra_settings=ex)
                st.start()
                self._stream, self._stream_sr = st, rate
                return rate
            except Exception as e:
                last = e
        raise RuntimeError(f"Could not open audio output: {last}")

    def _flush(self):
        with self._lock:
            self._gen += 1
            self._chunks.clear()

    def _push(self, kind, data=None, src=None, start=0):
        with self._lock:
            self._chunks.append((self._gen, kind, data, src, start))

    def _open_src(self, src, start=0.0):
        path = src.get("path") or ""
        headers = None
        if src.get("source", "local") != "local":
            if self.resolver is None:
                raise DecodeError("Streaming resolver unavailable")
            path, headers = self.resolver(src)
        dec = open_decoder(path, src.get("duration") or 0.0, headers)
        dec.gain = float(self.gain_for(src) or 1.0)
        if start > 0:
            dec.seek(start)
        return dec

    def _describe(self, dec, src):
        sub = dec.subtype or ""
        bits = {"PCM_16": 16, "PCM_24": 24, "PCM_32": 32, "FLOAT": 32, "DOUBLE": 64, "PCM_S8": 8, "PCM_U8": 8}.get(sub)
        self.format = {
            "samplerate": dec.samplerate, "channels": dec.channels, "subtype": sub,
            "bits": bits or src.get("bitdepth") or None, "device_rate": self._stream_sr,
            "resampled": self._resampler is not None,
        }
        self.formatChanged.emit(dict(self.format))

    def _start_track(self, src, start, autoplay):
        self._close_decoders()
        self._flush()
        self._set_state("buffering")
        try:
            dec = self._open_src(src, start)
        except Exception as e:
            self.error.emit(f"Cannot play “{src.get('title') or src.get('path')}”: {e}")
            self._set_state("stopped")
            self.trackEnded.emit({**src, "_failed": True})
            return
        rate = self._open_stream(dec.samplerate)
        self._resampler = None if rate == dec.samplerate else LinearResampler(dec.samplerate, rate)
        self._dec, self._src = dec, src
        self.loud.reset(dec.samplerate)
        if start > 0:
            self.loud.invalidate()
        self.dsp.reset()
        self.ring.clear()
        self.spectrum.sr = rate
        self._push("begin", src=src, start=int(start * rate))
        self._playing_src = src
        self._played = int(start * rate)
        self._describe(dec, src)
        self._paused = not autoplay
        self._set_state("playing" if autoplay else "paused")

    def _close_decoders(self):
        for d in (self._dec, self._next[0] if self._next else None):
            if d is not None:
                try:
                    d.close()
                except Exception:
                    pass
        self._dec = None
        self._next = None

    def _finish_analysis(self, src):
        if not self.loud.valid or src is None:
            return
        res = {"lufs": self.loud.integrated(), "peak": self.loud.peak_db(), "dr": self.loud.dr()}
        if res["lufs"] is not None:
            self.analysisDone.emit(src, res)

    def _peek_next(self):
        try:
            return self.next_provider() if self.next_provider else None
        except Exception:
            return None

    def _producer(self):
        while True:
            try:
                # ── commands
                block_wait = self._dec is None
                try:
                    cmd = self._cmd.get(timeout=0.05) if block_wait else self._cmd.get_nowait()
                except queue.Empty:
                    cmd = None
                if cmd:
                    op = cmd[0]
                    if op == "quit":
                        self._close_decoders()
                        return
                    if op == "load":
                        self._start_track(cmd[1], cmd[2], cmd[3])
                    elif op == "seek" and self._dec is not None:
                        self._flush()
                        if self._next:
                            self._next[0].close()
                            self._next = None
                        self._dec.seek(cmd[1])
                        self.loud.invalidate()
                        self.dsp.reset()
                        self._push("reset", src=self._src, start=int(cmd[1] * (self._stream_sr or 44100)))
                    elif op == "stop":
                        self._close_decoders()
                        self._flush()
                        self._src = None
                        self._playing_src = None
                        self._played = 0
                        self._paused = True
                        self._set_state("stopped")
                    elif op == "reopen":
                        if self._stream:
                            try:
                                self._stream.close()
                            except Exception:
                                pass
                            self._stream = None
                        if self._src is not None:
                            pos = self.position()
                            self._start_track(self._src, pos, not self._paused)
                    continue
                if self._dec is None:
                    continue
                with self._lock:
                    full = len(self._chunks) >= MAX_CHUNKS
                if full:
                    time.sleep(0.008)
                    continue
                self._decode_step()
            except Exception as e:
                traceback.print_exc()
                self.error.emit(str(e))
                self._close_decoders()
                self._set_state("stopped")

    def _decode_step(self):
        dec, sr = self._dec, self._dec.samplerate
        block = dec.read(BLOCK)
        if dec.gain != 1.0 and len(block):
            block = block * dec.gain
        self.loud.push(block)
        xf = float(self.s["crossfade"] or 0)

        # prepare crossfade partner
        if xf > 0 and self._next is None and dec.duration:
            pos_est = self._played / float(self._stream_sr or sr)
            remaining = dec.duration - pos_est - (MAX_CHUNKS * BLOCK / sr)
            if 0 < remaining <= xf and len(block):
                nsrc = self._peek_next()
                if nsrc and nsrc.get("source", "local") == "local":
                    try:
                        nd = self._open_src(nsrc)
                        if nd.samplerate == sr:
                            self._next = (nd, nsrc)
                            self._xf_total = max(BLOCK, int(remaining * sr))
                            self._xf_pos = 0
                            self._push("begin", src=nsrc, start=0)
                            self._finish_analysis(self._src)
                            self.loud.reset(sr)
                        else:
                            nd.close()
                    except Exception:
                        pass

        if self._next is not None:
            nd, nsrc = self._next
            nb = nd.read(BLOCK)
            if nd.gain != 1.0 and len(nb):
                nb = nb * nd.gain
            self.loud.push(nb)
            n = max(len(block), len(nb))
            a = np.zeros((n, 2), np.float32)
            b = np.zeros((n, 2), np.float32)
            a[: len(block)] = block
            ended_a = len(block) == 0
            b[: len(nb)] = nb
            t = np.clip((self._xf_pos + np.arange(n)) / self._xf_total, 0, 1)[:, None]
            block = (a * np.cos(t * np.pi / 2) + b * np.sin(t * np.pi / 2)).astype(np.float32)
            self._xf_pos += n
            if self._xf_pos >= self._xf_total or ended_a:
                dec.close()
                self._dec, self._src = nd, nsrc
                self._next = None
                self._describe(nd, nsrc)
            if len(block):
                self._emit_pcm(self.dsp.process(block, sr))
            return

        if len(block) == 0:
            # ── end of file → gapless continuation?
            self._finish_analysis(self._src)
            nsrc = self._peek_next()
            if nsrc is not None:
                try:
                    nd = self._open_src(nsrc)
                except Exception:
                    nd = None
                if nd is not None and nd.samplerate == sr:
                    dec.close()
                    self._dec, self._src = nd, nsrc
                    self.loud.reset(sr)
                    if not self.s["gapless"]:
                        self._emit_pcm(np.zeros((int(sr * 0.35), 2), np.float32))
                    self._push("begin", src=nsrc, start=0)
                    self._describe(nd, nsrc)
                    return
                if nd is not None:
                    nd.close()
            self._push("end", src=self._src)
            dec.close()
            self._dec = None
            return
        self._emit_pcm(self.dsp.process(block, sr))

    def _emit_pcm(self, x):
        if self._resampler is not None:
            x = self._resampler.process(x)
        if len(x):
            self._push("pcm", data=x)

    # ───────────────────────────── realtime callback (PortAudio thread)
    def _callback(self, outdata, frames, _time, _status):
        target = 0.0 if (self._paused or self.muted) else self.volume ** 1.6
        if self._paused and self._gain <= 1e-4:
            outdata.fill(0)
            self._gain = 0.0
            return
        out = np.zeros((frames, 2), np.float32)
        filled = 0
        while filled < frames:
            if self._left is None or self._left_gen != self._gen or len(self._left) == 0:
                self._left = None
                with self._lock:
                    item = self._chunks.popleft() if self._chunks else None
                if item is None:
                    break
                gen, kind, data, src, start = item
                if gen != self._gen:
                    continue
                if kind == "begin":
                    self._playing_src = src
                    self._played = start
                    self.trackStarted.emit(src)
                    continue
                if kind == "reset":
                    self._played = start
                    continue
                if kind == "end":
                    self.trackEnded.emit(src)
                    continue
                self._left, self._left_gen = data, gen
            n = min(frames - filled, len(self._left))
            out[filled: filled + n] = self._left[:n]
            self._left = self._left[n:]
            filled += n
            self._played += n
        self.ring.push(out)
        fade = max(0.005, self.s["fade_pause_ms"] / 1000.0)
        step = frames / ((self._stream_sr or 44100) * fade)
        g0 = self._gain
        g1 = g0 + max(-step, min(step, target - g0)) if abs(target - g0) > 1e-4 else target
        if self.muted and not self._paused:
            g1 = target
        self._gain = g1
        if abs(g1 - g0) > 1e-5:
            out *= np.linspace(g0, g1, frames, dtype=np.float32)[:, None]
        else:
            out *= g1
        outdata[:] = out
