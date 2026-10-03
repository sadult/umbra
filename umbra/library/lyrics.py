"""Lyrics: .lrc side-cars, embedded tags and LRCLIB (online, free, no key)."""
import hashlib
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..config import APP_NAME, APP_VERSION, cache_dir
from .tags import read_tags

TS = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)\]")


def parse_lrc(text: str):
    """Return list[(seconds, line)] if text contains timestamps, else None."""
    if not text or not TS.search(text):
        return None
    offset = 0.0
    m = re.search(r"\[offset:\s*([+-]?\d+)\]", text, re.I)
    if m:
        offset = int(m.group(1)) / 1000.0
    out = []
    for raw in text.splitlines():
        stamps = TS.findall(raw)
        if not stamps:
            continue
        line = TS.sub("", raw).strip()
        line = re.sub(r"<\d+:\d+(?:\.\d+)?>", "", line)  # enhanced word stamps
        for mm, ss in stamps:
            t = int(mm) * 60 + float(ss.replace(":", "."))
            out.append((max(0.0, t - offset), line))
    out.sort(key=lambda x: x[0])
    return out or None


class Lyrics:
    def __init__(self, kind="none", source="", synced=None, plain=""):
        self.kind = kind          # synced | plain | none | loading | instrumental
        self.source = source      # "LRC file" | "Embedded" | "LRCLIB" ...
        self.synced = synced or []
        self.plain = plain

    @classmethod
    def from_text(cls, text, source):
        syn = parse_lrc(text)
        if syn:
            return cls("synced", source, syn, "\n".join(l for _, l in syn))
        if text and text.strip():
            return cls("plain", source, None, text.strip())
        return None


def _cache_path(t):
    key = f"{(t.get('artist') or '').lower()}|{(t.get('title') or '').lower()}|{int(t.get('duration') or 0)}"
    return cache_dir("lyrics") / (hashlib.md5(key.encode()).hexdigest() + ".json")


def lrclib_fetch(t, timeout=8):
    ua = f"{APP_NAME}/{APP_VERSION} (https://github.com/)"
    artist = t.get("artist") or ""
    title = t.get("title") or ""
    if not title:
        return None
    params = {"artist_name": artist, "track_name": title}
    if t.get("album"):
        params["album_name"] = t["album"]
    if t.get("duration"):
        params["duration"] = int(round(t["duration"]))
    urls = ["https://lrclib.net/api/get?" + urllib.parse.urlencode(params),
            "https://lrclib.net/api/search?" + urllib.parse.urlencode({"track_name": title, "artist_name": artist})]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
        if isinstance(data, list):
            dur = float(t.get("duration") or 0)
            if dur:
                data = [d for d in data if abs((d.get("duration") or dur) - dur) <= 4] or []
            data = next((d for d in data if d.get("syncedLyrics")), data[0] if data else None)
        if not data:
            continue
        if data.get("instrumental"):
            return {"instrumental": True}
        if data.get("syncedLyrics") or data.get("plainLyrics"):
            return {"synced": data.get("syncedLyrics") or "", "plain": data.get("plainLyrics") or ""}
    return None


def lrclib_search(query="", artist="", title="", timeout=10):
    """Free-text LRCLIB search. Returns a list of candidates (dicts) — synced ones first."""
    ua = f"{APP_NAME}/{APP_VERSION} (https://github.com/sadult/umbra)"
    params = {"q": query} if query else {"track_name": title, "artist_name": artist}
    req = urllib.request.Request("https://lrclib.net/api/search?" + urllib.parse.urlencode(params), headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8")) or []
    out = []
    for d in data:
        if not (d.get("syncedLyrics") or d.get("plainLyrics") or d.get("instrumental")):
            continue
        out.append({"title": d.get("trackName") or "", "artist": d.get("artistName") or "", "album": d.get("albumName") or "",
                    "duration": d.get("duration") or 0, "synced": d.get("syncedLyrics") or "",
                    "plain": d.get("plainLyrics") or "", "instrumental": bool(d.get("instrumental"))})
    out.sort(key=lambda d: (not d["synced"], d["instrumental"]))
    return out


def save_lyrics(t, text, embed=False):
    """Attach lyrics to a track. Local files get a side-car .lrc (synced) or embedded tag;
    streams (and everything else) are stored in the lyrics cache so they load next time."""
    from .tags import write_tags
    where = "cache"
    if t.get("source", "local") == "local" and t.get("path"):
        p = Path(t["path"])
        try:
            if embed or not parse_lrc(text):
                write_tags(str(p), {"lyrics": text})
                where = "embedded tag"
            else:
                p.with_suffix(".lrc").write_text(text, "utf-8")
                where = p.with_suffix(".lrc").name
        except Exception:
            where = "cache"
    synced = text if parse_lrc(text) else ""
    try:
        _cache_path(t).write_text(json.dumps({"synced": synced, "plain": "" if synced else text}, ensure_ascii=False), "utf-8")
    except Exception:
        pass
    return where


def load_lyrics(t, online=True) -> Lyrics:
    path = t.get("path") or ""
    if t.get("source", "local") == "local" and path:
        lrc = Path(path).with_suffix(".lrc")
        if lrc.exists():
            try:
                raw = lrc.read_bytes()
                for enc in ("utf-8-sig", "utf-16", "cp1256", "latin-1"):
                    try:
                        l = Lyrics.from_text(raw.decode(enc), "LRC file")
                        if l:
                            return l
                        break
                    except UnicodeDecodeError:
                        continue
            except Exception:
                pass
        try:
            emb = read_tags(path).get("lyrics") or ""
            l = Lyrics.from_text(emb, "Embedded")
            if l:
                return l
        except Exception:
            pass
    cp = _cache_path(t)
    if cp.exists():
        try:
            d = json.loads(cp.read_text("utf-8"))
            if d.get("instrumental"):
                return Lyrics("instrumental", "LRCLIB")
            l = Lyrics.from_text(d.get("synced") or d.get("plain") or "", "LRCLIB")
            if l:
                return l
        except Exception:
            pass
    if online:
        d = lrclib_fetch(t)
        if d:
            try:
                cp.write_text(json.dumps(d, ensure_ascii=False), "utf-8")
            except Exception:
                pass
            if d.get("instrumental"):
                return Lyrics("instrumental", "LRCLIB")
            l = Lyrics.from_text(d.get("synced") or d.get("plain") or "", "LRCLIB")
            if l:
                return l
    return Lyrics("none")


class LyricsLoader(QObject):
    loaded = Signal(object, object)   # track id, Lyrics

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self._token = 0

    def request(self, t):
        self._token += 1
        tok = self._token

        def run():
            try:
                l = load_lyrics(t, self.s["online_lyrics"])
            except Exception:
                l = Lyrics("none")
            if tok == self._token:
                self.loaded.emit(t.get("id"), l)
        threading.Thread(target=run, daemon=True).start()

    def forget(self, t):
        try:
            _cache_path(t).unlink()
        except Exception:
            pass


def has_lyrics(t):
    """True if lyrics are already available offline (side-car, embedded or cached)."""
    try:
        return load_lyrics(t, online=False).kind != "none"
    except Exception:
        return False


class LyricsBatch(QObject):
    """Walks through many tracks and fetches lyrics from LRCLIB, one at a time (polite rate)."""
    progress = Signal(int, int, int, str)    # done, total, found, current "artist — title"
    finished = Signal(int, int, int, bool)   # found, total, skipped(already had), cancelled

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self._stop = threading.Event()
        self.running = False
        self.state = (0, 0, 0, "")

    def start(self, tracks, mode=None, only_missing=True):
        """mode: 'lrc' (side-car .lrc / tag for plain text) · 'embed' (inside the file) · 'cache' (don't touch files)."""
        if self.running:
            return False
        tracks = [dict(t) for t in tracks if t and t.get("title")]
        if not tracks:
            return False
        mode = mode or self.s["lyrics_batch_mode"] or "lrc"
        self._stop.clear()
        self.running = True
        threading.Thread(target=self._run, args=(tracks, mode, only_missing), daemon=True).start()
        return True

    def cancel(self):
        self._stop.set()

    def _run(self, tracks, mode, only_missing):
        total, found, skipped = len(tracks), 0, 0
        for i, t in enumerate(tracks):
            if self._stop.is_set():
                break
            label = f"{t.get('artist') or 'Unknown'} — {t.get('title')}"
            self.state = (i, total, found, label)
            self.progress.emit(i, total, found, label)
            try:
                local = t.get("source", "local") == "local"
                have = load_lyrics(t, online=False) if only_missing else Lyrics("none")
                if have.kind != "none":
                    on_disk = have.source in ("LRC file", "Embedded")
                    if mode == "cache" or not local or on_disk or have.kind == "instrumental":
                        skipped += 1
                        continue
                    # cached from an earlier play → write it to the file without hitting the network
                    try:
                        cd = json.loads(_cache_path(t).read_text("utf-8"))
                        text = cd.get("synced") or cd.get("plain")
                    except Exception:
                        text = None
                    if text:
                        save_lyrics(t, text, embed=(mode == "embed"))
                        found += 1
                        continue
                d = lrclib_fetch(t)
                if d and d.get("instrumental"):
                    _cache_path(t).write_text(json.dumps(d), "utf-8")
                    found += 1
                elif d and (d.get("synced") or d.get("plain")):
                    text = d.get("synced") or d.get("plain")
                    if mode == "cache" or t.get("source", "local") != "local":
                        _cache_path(t).write_text(json.dumps(d, ensure_ascii=False), "utf-8")
                    else:
                        save_lyrics(t, text, embed=(mode == "embed"))
                    found += 1
            except Exception:
                pass
            time.sleep(0.12)
        self.running = False
        self.state = (total, total, found, "")
        self.progress.emit(total, total, found, "")
        self.finished.emit(found, total, skipped, self._stop.is_set())
