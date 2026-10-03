"""Playback controller: queue, shuffle/repeat, play counting, session restore."""
import random
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .audio.engine import AudioEngine
from .library import streaming


class Player(QObject):
    trackChanged = Signal(object)      # track dict or None
    stateChanged = Signal(str)
    queueChanged = Signal()
    favoriteChanged = Signal(int, bool)
    shuffleChanged = Signal(bool)
    repeatChanged = Signal(str)
    volumeChanged = Signal(float)
    message = Signal(str)
    analysisUpdated = Signal(int)
    sleepChanged = Signal(object)      # remaining seconds (int) · "end" · None

    def __init__(self, lib, settings):
        super().__init__()
        self.lib, self.s = lib, settings
        self.engine = AudioEngine(settings, resolver=self._resolve)
        self.engine.next_provider = self._peek_next
        self.engine.gain_for = self._gain_for
        self.engine.trackStarted.connect(self._on_started)
        self.engine.trackEnded.connect(self._on_ended)
        self.engine.stateChanged.connect(self.stateChanged)
        self.engine.error.connect(self.message)
        self.engine.analysisDone.connect(self._on_analysis)
        self.queue: list[int] = []
        self.original: list[int] | None = None
        self.index = -1
        self.shuffle = bool(settings["shuffle"])
        self.repeat = settings["repeat"]
        self.current = None
        self._counted = False
        self._snapshot = ([], -1, "off")
        self._shown = None
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start(500)
        settings.changed.connect(self._on_setting)
        self._sleep_at = None          # monotonic deadline
        self._sleep_end = False        # stop after the current track
        self._sleep_vol = None
        self._sleep_t = QTimer(self)
        self._sleep_t.timeout.connect(self._sleep_tick)

    # ── sleep timer
    def set_sleep(self, minutes):
        """minutes: int → pause after that long (with a 20 s fade) · "end" → after this track · None/0 → off."""
        self._sleep_restore()
        self._sleep_end = minutes == "end"
        self._sleep_at = time.monotonic() + float(minutes) * 60 if minutes and minutes != "end" else None
        if self._sleep_at:
            self._sleep_t.start(1000)
        else:
            self._sleep_t.stop()
        self.sleepChanged.emit(self.sleep_remaining())

    def sleep_remaining(self):
        if self._sleep_end:
            return "end"
        if self._sleep_at:
            return max(0, int(self._sleep_at - time.monotonic()))
        return None

    def _sleep_restore(self):
        if self._sleep_vol is not None:
            self.engine.set_volume(self._sleep_vol)
            self._sleep_vol = None

    def _sleep_fire(self):
        self._sleep_at, self._sleep_end = None, False
        self._sleep_t.stop()
        if self.engine.state == "playing":
            self.engine.pause()
        QTimer.singleShot(600, self._sleep_restore)
        self.message.emit("Sleep timer — playback paused. Good night.")
        self.sleepChanged.emit(None)

    def _sleep_tick(self):
        left = self.sleep_remaining()
        if left is None or left == "end":
            return
        if left <= 20 and self.engine.state == "playing":
            if self._sleep_vol is None:
                self._sleep_vol = self.engine.volume
            self.engine.set_volume(self._sleep_vol * max(0.0, left / 20.0))
        if left <= 0:
            self._sleep_fire()
        else:
            self.sleepChanged.emit(left)

    # ── helpers
    @staticmethod
    def _resolve(src):
        """Streams that were downloaded play from disk; everything else is resolved through yt-dlp."""
        try:
            from .ui.context import ctx
            f = ctx.downloads.local_file(src) if ctx.downloads else None
            if f:
                return f, None
        except Exception:
            pass
        return streaming.resolve(src)

    def _src(self, tid, qindex):
        t = self.lib.get(tid)
        if not t:
            return None
        d = dict(t)
        d["qindex"] = qindex
        return d

    def _gain_for(self, src):
        mode = self.s["leveling"]
        pre = float(self.s["leveling_preamp"])
        db = None
        if mode == "rg_track":
            db = src.get("rg_track") if src.get("rg_track") is not None else src.get("rg_album")
        elif mode == "rg_album":
            db = src.get("rg_album") if src.get("rg_album") is not None else src.get("rg_track")
        elif mode == "smart" and src.get("lufs") is not None:
            db = float(self.s["leveling_target"]) - float(src["lufs"])
            if src.get("peak") is not None:
                db = min(db, -0.5 - float(src["peak"]) + 3.0)  # limiter catches the rest
        if db is None:
            return 10 ** (pre / 20) if mode != "off" else 1.0
        return 10 ** ((db + pre) / 20)

    def _peek_next(self):
        if self._sleep_end:
            return None
        q, i, rep = self._snapshot
        if not q or i < 0:
            return None
        if rep == "one":
            return self._src(q[i], i)
        if i + 1 < len(q):
            return self._src(q[i + 1], i + 1)
        if rep == "all":
            return self._src(q[0], 0)
        return None

    def _sync(self):
        self._snapshot = (list(self.queue), self.index, self.repeat)

    def _on_setting(self, key, v):
        if key in ("output_device", "exclusive", "buffer_ms"):
            self.engine.restart_output()

    # ── engine callbacks
    def _on_started(self, src):
        qi = src.get("qindex", self.index)
        if 0 <= qi < len(self.queue) and self.queue[qi] == src.get("id"):
            self.index = qi
        self.current = self.lib.get(src.get("id")) or src
        self._counted = False
        self._sync()
        key = (src.get("id"), qi)
        if key != self._shown:
            self._shown = key
            self.trackChanged.emit(self.current)
            self.queueChanged.emit()

    def _on_ended(self, src):
        if src.get("_failed"):
            if self.index + 1 < len(self.queue):
                QTimer.singleShot(400, lambda: self.play_index(self.index + 1))
            return
        if self._sleep_end:
            self.engine.pause()
            self.engine.seek(0)
            if self.index + 1 < len(self.queue):
                QTimer.singleShot(0, lambda: self.play_index(self.index + 1, autoplay=False))
            self._sleep_fire()
            return
        if self.repeat == "one" and self.current:
            self.play_index(self.index)
            return
        if self.index + 1 < len(self.queue):
            self.play_index(self.index + 1)
        elif self.repeat == "all" and self.queue:
            self.play_index(0)
        else:
            self.engine.pause()
            self.engine.seek(0)

    def _on_analysis(self, src, res):
        tid = src.get("id")
        if tid and res.get("lufs") is not None:
            self.lib.update(tid, lufs=round(res["lufs"], 2), peak=round(res["peak"] or 0, 2),
                            dr=round(res["dr"], 1) if res.get("dr") is not None else None)
            self.analysisUpdated.emit(tid)

    def _on_tick(self):
        if not self.current or self._counted or self.engine.state != "playing":
            return
        dur = self.engine.duration() or self.current.get("duration") or 0
        pos = self.engine.position()
        if dur and (pos >= dur * float(self.s["play_count_threshold"]) or pos >= 240):
            self._counted = True
            self.lib.mark_played(self.current["id"])

    # ── transport
    def play_tracks(self, ids, start=0, shuffle=None):
        ids = [i for i in ids if i is not None]
        if not ids:
            return
        if shuffle is not None and shuffle != self.shuffle:
            self.shuffle = shuffle
            self.s.set("shuffle", shuffle)
            self.shuffleChanged.emit(shuffle)
        if self.shuffle:
            first = ids[start] if shuffle is None else random.choice(ids)
            rest = [i for k, i in enumerate(ids) if i != first]
            random.shuffle(rest)
            self.original = list(ids)
            self.queue = [first] + rest
            start = 0
        else:
            self.original = None
            self.queue = list(ids)
        self.play_index(start)

    def play_index(self, i, start=0.0, autoplay=True):
        if not (0 <= i < len(self.queue)):
            return
        self._maybe_skip()
        self.index = i
        self._sync()
        src = self._src(self.queue[i], i)
        if src is None:
            return
        self.current = self.lib.get(src["id"]) or src
        self._counted = False
        self._shown = (src["id"], i)
        self.engine.load(src, start, autoplay)
        self.trackChanged.emit(self.current)
        self.queueChanged.emit()

    def _maybe_skip(self):
        if self.current and self.engine.state == "playing":
            dur = self.engine.duration() or 0
            if dur and self.engine.position() < dur * 0.3 and not self._counted:
                try:
                    self.lib.mark_skipped(self.current["id"])
                except Exception:
                    pass

    def toggle(self):
        if self.current is None and self.queue:
            self.play_index(max(0, self.index))
            return
        if self.engine.state == "stopped" and self.current:
            self.play_index(self.index)
            return
        self.engine.toggle()

    def next(self):
        if not self.queue:
            return
        if self.index + 1 < len(self.queue):
            self.play_index(self.index + 1)
        elif self.repeat != "off":
            self.play_index(0)

    def prev(self):
        if not self.queue:
            return
        if self.engine.position() > 3.5:
            self.seek(0)
        elif self.index > 0:
            self.play_index(self.index - 1)
        else:
            self.seek(0)

    def seek(self, sec):
        self.engine.seek(max(0.0, sec))

    def seek_rel(self, d):
        self.seek(self.engine.position() + d)

    def set_volume(self, v):
        v = max(0.0, min(1.0, v))
        self.engine.set_volume(v)
        self.s.set("volume", round(v, 3), emit=False)
        self.volumeChanged.emit(v)

    def toggle_mute(self):
        self.engine.muted = not self.engine.muted
        self.s.set("muted", self.engine.muted, emit=False)
        self.volumeChanged.emit(self.engine.volume)

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.s.set("shuffle", self.shuffle)
        cur = self.queue[self.index] if 0 <= self.index < len(self.queue) else None
        if self.shuffle:
            self.original = list(self.queue)
            up = self.queue[self.index + 1:]
            random.shuffle(up)
            self.queue = self.queue[: self.index + 1] + up
        elif self.original:
            self.queue = list(self.original)
            self.original = None
            if cur in self.queue:
                self.index = self.queue.index(cur)
        self._sync()
        self.shuffleChanged.emit(self.shuffle)
        self.queueChanged.emit()

    def cycle_repeat(self):
        self.repeat = {"off": "all", "all": "one", "one": "off"}[self.repeat]
        self.s.set("repeat", self.repeat)
        self._sync()
        self.repeatChanged.emit(self.repeat)

    # ── queue editing
    def add_to_queue(self, ids):
        ids = list(ids)
        if not self.queue:
            self.play_tracks(ids)
            return
        self.queue.extend(ids)
        if self.original is not None:
            self.original.extend(ids)
        self._sync()
        self.queueChanged.emit()
        self.message.emit(f"Added {len(ids)} track{'s' if len(ids) != 1 else ''} to queue")

    def play_next(self, ids):
        ids = list(ids)
        if not self.queue:
            self.play_tracks(ids)
            return
        self.queue[self.index + 1:self.index + 1] = ids
        self._sync()
        self.queueChanged.emit()
        self.message.emit("Playing next")

    def remove_at(self, positions):
        positions = sorted(set(positions), reverse=True)
        for p in positions:
            if 0 <= p < len(self.queue) and p != self.index:
                del self.queue[p]
                if p < self.index:
                    self.index -= 1
        self._sync()
        self.queueChanged.emit()

    def move(self, src, dst):
        if not (0 <= src < len(self.queue)) or not (0 <= dst < len(self.queue)):
            return
        cur = self.queue[self.index] if self.index >= 0 else None
        tid = self.queue.pop(src)
        self.queue.insert(dst, tid)
        if cur is not None:
            # keep pointer on the same queue slot identity
            if src == self.index:
                self.index = dst
            elif src < self.index <= dst:
                self.index -= 1
            elif dst <= self.index < src:
                self.index += 1
        self._sync()
        self.queueChanged.emit()

    def set_upcoming(self, ids):
        self.queue = self.queue[: self.index + 1] + list(ids)
        self._sync()
        self.queueChanged.emit()

    def clear_upcoming(self):
        self.queue = self.queue[: self.index + 1]
        self.original = None
        self._sync()
        self.queueChanged.emit()

    def shuffle_upcoming(self):
        up = self.queue[self.index + 1:]
        random.shuffle(up)
        self.set_upcoming(up)

    def add_similar(self, n=15):
        t = self.current
        if not t:
            return
        inq = set(self.queue)
        pool = []
        if t.get("genre"):
            pool += self.lib.tracks("lower(genre)=lower(?) AND id<>?", (t["genre"], t["id"]), order="RANDOM()", limit=60)
        if t.get("artist"):
            pool += self.lib.tracks("lower(artist)=lower(?) AND id<>?", (t["artist"], t["id"]), order="RANDOM()", limit=20)
        if t.get("year"):
            pool += self.lib.tracks("year BETWEEN ? AND ? AND id<>?", (t["year"] - 3, t["year"] + 3, t["id"]), order="RANDOM()", limit=20)
        seen, ids = set(), []
        random.shuffle(pool)
        for r in pool:
            if r["id"] not in inq and r["id"] not in seen:
                seen.add(r["id"])
                ids.append(r["id"])
            if len(ids) >= n:
                break
        if ids:
            self.add_to_queue(ids)
        else:
            self.message.emit("No similar tracks found")

    def add_current_artist(self):
        t = self.current
        if t:
            ids = [r["id"] for r in self.lib.artist_tracks(t.get("artist") or "", "album") if r["id"] not in set(self.queue)]
            self.add_to_queue(ids) if ids else self.message.emit("Nothing new from this artist")

    def add_current_album(self):
        t = self.current
        if t and t.get("album"):
            aa = t.get("albumartist") or t.get("artist") or "Unknown Artist"
            ids = [r["id"] for r in self.lib.album_tracks(t["album"], aa) if r["id"] not in set(self.queue)]
            self.add_to_queue(ids) if ids else self.message.emit("Album already queued")

    # ── favourites
    def toggle_favorite(self, tid=None):
        tid = tid or (self.current or {}).get("id")
        if not tid:
            return
        t = self.lib.get(tid)
        fav = not bool(t and t.get("favorite"))
        self.lib.set_favorite(tid, fav)
        if self.current and self.current.get("id") == tid:
            self.current = self.lib.get(tid)
        self.favoriteChanged.emit(tid, fav)

    def is_favorite(self, tid=None):
        tid = tid or (self.current or {}).get("id")
        t = self.lib.get(tid) if tid else None
        return bool(t and t.get("favorite"))

    # ── session
    def save_session(self):
        if not self.queue:
            self.s.set("session", None, emit=False)
            return
        self.s.set("session", {"queue": self.queue[:2000], "index": self.index,
                               "pos": round(self.engine.position(), 1)}, emit=False)
        self.s.save()

    def restore_session(self):
        ses = self.s["session"]
        if not ses or not self.s["resume_session"]:
            return
        q = [i for i in ses.get("queue", []) if self.lib.get(i)]
        if not q:
            return
        self.queue = q
        idx = min(max(0, ses.get("index", 0)), len(q) - 1)
        self.index = idx
        self.play_index(idx, ses.get("pos", 0.0), autoplay=False)

    def shutdown(self):
        self.save_session()
        self.engine.shutdown()
