"""Download YouTube Music / Spotify-matched tracks to disk (yt-dlp), tag them and add them to the library."""
import os
import re
import shutil
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import streaming
from .tags import read_tags, write_tags

FFMPEG = shutil.which("ffmpeg")


def default_dir():
    d = Path.home() / "Music" / "Umbra Downloads"
    return str(d)


def _safe(s):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", s or "").strip().rstrip(".")
    return s[:120] or "Unknown"


class Downloader(QObject):
    progress = Signal(str, float)     # stream path, 0..1
    finished = Signal(str, str)       # stream path, local file
    failed = Signal(str, str)         # stream path, error
    batch = Signal(int, int, int)     # done, total, failed — for multi-track downloads
    registered = Signal(str, int)     # stream path, new local track id (main thread)

    MAX_PARALLEL = 3

    def __init__(self, lib, settings):
        super().__init__()
        self.lib, self.s = lib, settings
        self.active = {}              # stream path -> progress
        self._sem = threading.Semaphore(self.MAX_PARALLEL)
        self._b = [0, 0, 0]           # done, total, failed of the current batch
        self.finished.connect(self._register)
        self.failed.connect(lambda *_: self._tick(failed=True))

    # ── state
    def state(self, t):
        """None | float progress | 'done'"""
        p = t.get("path")
        if p in self.active:
            return self.active[p]
        f = (self.s["downloaded"] or {}).get(p)
        if f and os.path.exists(f):
            return "done"
        return None

    def local_file(self, t):
        f = (self.s["downloaded"] or {}).get(t.get("path"))
        return f if f and os.path.exists(f) else None

    # ── work
    def download(self, t):
        if not t or t.get("source", "local") == "local":
            return False
        if not streaming.available():
            self.failed.emit(t.get("path", ""), "yt-dlp is not installed (pip install yt-dlp)")
            return False
        key = t["path"]
        if key in self.active or self.state(t) == "done":
            return False
        self.active[key] = 0.0
        self.progress.emit(key, 0.0)
        if len(self.active) == 1:
            self._b = [0, 0, 0]
        self._b[1] += 1
        threading.Thread(target=self._run, args=(dict(t),), daemon=True).start()
        return True

    def download_many(self, tracks):
        """Queue several tracks (max 3 run at once). Returns how many were queued."""
        n = 0
        for t in tracks:
            if t and t.get("source", "local") != "local" and self.state(t) is None:
                n += bool(self.download(t))
        return n

    def pending(self, tracks):
        return [t for t in tracks if t.get("source", "local") != "local" and self.state(t) != "done"]

    def busy(self):
        return bool(self.active)

    def local_id(self, t):
        """Library id of the downloaded copy of a stream track (or None)."""
        f = self.local_file(t)
        if not f:
            return None
        r = self.lib.q("SELECT id FROM tracks WHERE path=?", (f,))
        return r[0]["id"] if r else None

    def prefer_local(self, ids):
        out = []
        for i in ids:
            t = self.lib.get(i)
            out.append((self.local_id(t) if t else None) or i)
        return out

    def _tick(self, failed=False):
        self._b[2 if failed else 0] += 1
        if self._b[1] > 1:
            self.batch.emit(self._b[0], self._b[1], self._b[2])

    def _run(self, t):
        with self._sem:
            self._run_one(t)

    def _run_one(self, t):
        key = t["path"]
        try:
            out_dir = Path(self.s["download_dir"] or default_dir())
            out_dir.mkdir(parents=True, exist_ok=True)
            artist, title = t.get("artist") or "", t.get("title") or "Untitled"
            stem = _safe(f"{artist} - {title}" if artist else title)
            if t.get("source") == "spotify" or not t.get("url"):
                target = f"ytsearch1:{artist} - {title} audio"
            else:
                target = t["url"]
            fmt = self.s["download_format"] if FFMPEG else "native"

            def hook(d):
                if d.get("status") == "downloading":
                    tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    if tot:
                        k = min(0.97, d.get("downloaded_bytes", 0) / tot)
                        self.active[key] = k
                        self.progress.emit(key, k)
            opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 15,
                    "outtmpl": str(out_dir / (stem + ".%(ext)s")), "progress_hooks": [hook],
                    "format": "bestaudio[ext=m4a]/bestaudio/best"}
            from .streaming import auth_opts
            opts.update(auth_opts())
            if fmt != "native":
                pp = {"key": "FFmpegExtractAudio", "preferredcodec": fmt}
                if fmt == "mp3":
                    pp["preferredquality"] = "320"
                opts["postprocessors"] = [pp]
            import yt_dlp
            with yt_dlp.YoutubeDL(opts) as y:
                info = y.extract_info(target, download=True)
                if "entries" in info:
                    info = (info.get("entries") or [None])[0] or {}
            # locate the produced file
            cands = sorted(out_dir.glob(stem + ".*"), key=lambda p: p.stat().st_mtime, reverse=True)
            cands = [c for c in cands if c.suffix.lower() not in (".part", ".ytdl", ".webp", ".jpg", ".png")]
            if not cands:
                raise RuntimeError("Download finished but no audio file was produced")
            f = str(cands[0])
            # tags + artwork
            art = None
            thumb = t.get("thumb") or info.get("thumbnail")
            if thumb:
                try:
                    req = urllib.request.Request(thumb, headers={"User-Agent": streaming.UA})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        art = r.read()
                except Exception:
                    art = None
            try:
                write_tags(f, {"title": title, "artist": artist, "albumartist": artist,
                               "album": t.get("album") or "", "genre": t.get("genre") or ""}, art)
            except Exception:
                pass
            self.finished.emit(key, f)
        except Exception as e:
            self.active.pop(key, None)
            self.failed.emit(key, str(e).splitlines()[0][:200] if str(e) else "Download failed")

    def _register(self, key, f):
        """Main thread: remember the file, add it to the library."""
        self.active.pop(key, None)
        self._tick()
        d = dict(self.s["downloaded"] or {})
        d[key] = f
        self.s.set("downloaded", d)
        try:
            st = os.stat(f)
            rec = read_tags(f)
            rec.pop("lyrics", None)
            folder = str(Path(self.s["download_dir"] or default_dir()))
            rec.update(path=f, source="local", filesize=st.st_size, mtime=st.st_mtime, folder=folder)
            rec.setdefault("added", __import__("time").time())
            nid = self.lib.upsert(rec)
            old = self.lib.q("SELECT id FROM tracks WHERE path=?", (key,))
            if old:
                self.lib.replace_track(old[0]["id"], nid)
                try:   # carry over plays & favorite
                    o = self.lib.get(old[0]["id"])
                    self.lib.update(nid, play_count=o.get("play_count") or 0, favorite=o.get("favorite") or 0)
                except Exception:
                    pass
            self.registered.emit(key, nid)
            if self.s["download_add_library"] and folder not in self.lib.folders():
                self.lib.add_folder(folder)
            self.lib.invalidate()
        except Exception as e:
            print("register download failed:", e)
