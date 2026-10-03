"""SQLite-backed music library."""
import random
import sqlite3
import threading
import time

from ..config import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT UNIQUE NOT NULL,
  source TEXT DEFAULT 'local',
  url TEXT, thumb TEXT,
  title TEXT, artist TEXT, albumartist TEXT, album TEXT, genre TEXT,
  year INTEGER DEFAULT 0, track INTEGER DEFAULT 0, tracktotal INTEGER DEFAULT 0,
  disc INTEGER DEFAULT 0, disctotal INTEGER DEFAULT 0, composer TEXT, comment TEXT,
  duration REAL DEFAULT 0, bitrate INTEGER DEFAULT 0, samplerate INTEGER DEFAULT 0,
  bitdepth INTEGER DEFAULT 0, channels INTEGER DEFAULT 0, codec TEXT, lossless INTEGER DEFAULT 0,
  filesize INTEGER DEFAULT 0, mtime REAL DEFAULT 0, added REAL DEFAULT 0,
  play_count INTEGER DEFAULT 0, skip_count INTEGER DEFAULT 0, last_played REAL,
  favorite INTEGER DEFAULT 0, rating INTEGER DEFAULT 0,
  has_art INTEGER DEFAULT 0, rg_track REAL, rg_album REAL,
  lufs REAL, peak REAL, dr REAL, folder TEXT
);
CREATE INDEX IF NOT EXISTS ix_album ON tracks(album, albumartist);
CREATE INDEX IF NOT EXISTS ix_artist ON tracks(artist);
CREATE TABLE IF NOT EXISTS folders(path TEXT PRIMARY KEY, added REAL);
CREATE TABLE IF NOT EXISTS playlists(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, created REAL,
  description TEXT DEFAULT '', smart TEXT);
CREATE TABLE IF NOT EXISTS playlist_items(playlist_id INTEGER, track_id INTEGER, pos INTEGER);
CREATE TABLE IF NOT EXISTS history(track_id INTEGER, ts REAL);
"""

TRACK_COLS = ["path", "source", "url", "thumb", "title", "artist", "albumartist", "album", "genre", "year",
              "track", "tracktotal", "disc", "disctotal", "composer", "comment", "duration", "bitrate",
              "samplerate", "bitdepth", "channels", "codec", "lossless", "filesize", "mtime",
              "has_art", "rg_track", "rg_album", "folder"]

ORDERS = {
    "title": "title COLLATE NOCASE",
    "artist": "COALESCE(NULLIF(albumartist,''),artist) COLLATE NOCASE, album COLLATE NOCASE, disc, track",
    "album": "album COLLATE NOCASE, disc, track",
    "added": "added DESC",
    "duration": "duration DESC",
    "plays": "play_count DESC",
    "year": "year DESC, album COLLATE NOCASE, disc, track",
}


def album_artist(t):
    return (t.get("albumartist") or t.get("artist") or "Unknown Artist").strip()


def album_key(t):
    return f"{album_artist(t).lower()}\x1f{(t.get('album') or '').strip().lower()}"


class Library:
    def __init__(self, path=None):
        self.path = path or str(data_dir() / "library.db")
        self.lock = threading.RLock()
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(SCHEMA)
        cols = {r[1] for r in self.con.execute("PRAGMA table_info(playlists)")}
        for c, ddl in (("origin", "TEXT"), ("link", "TEXT"), ("thumb", "TEXT"), ("synced", "REAL")):
            if c not in cols:
                self.con.execute(f"ALTER TABLE playlists ADD COLUMN {c} {ddl}")
        self.con.commit()
        self._cache = {}

    # ── basic
    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def x(self, sql, args=(), commit=True):
        with self.lock:
            cur = self.con.execute(sql, args)
            if commit:
                self.con.commit()
            return cur

    def get(self, tid):
        if tid in self._cache:
            return self._cache[tid]
        r = self.q("SELECT * FROM tracks WHERE id=?", (tid,))
        if r:
            self._cache[tid] = r[0]
            return r[0]
        return None

    def get_many(self, ids):
        missing = [i for i in ids if i not in self._cache]
        for i in range(0, len(missing), 500):
            chunk = missing[i:i + 500]
            for r in self.q(f"SELECT * FROM tracks WHERE id IN ({','.join('?' * len(chunk))})", chunk):
                self._cache[r["id"]] = r
        return [self._cache[i] for i in ids if i in self._cache]

    def invalidate(self, tid=None):
        if tid is None:
            self._cache.clear()
        else:
            self._cache.pop(tid, None)

    # ── writes
    def upsert(self, d: dict, commit=True):
        cols = [c for c in TRACK_COLS if c in d]
        with self.lock:
            row = self.con.execute("SELECT id FROM tracks WHERE path=?", (d["path"],)).fetchone()
            if row:
                self.con.execute(f"UPDATE tracks SET {','.join(c + '=?' for c in cols)} WHERE id=?",
                                 [d[c] for c in cols] + [row[0]])
                tid = row[0]
            else:
                cur = self.con.execute(
                    f"INSERT INTO tracks({','.join(cols)},added) VALUES({','.join('?' * len(cols))},?)",
                    [d[c] for c in cols] + [d.get("added") or time.time()])
                tid = cur.lastrowid
            if commit:
                self.con.commit()
        self.invalidate(tid)
        return tid

    def commit(self):
        with self.lock:
            self.con.commit()

    def update(self, tid, **kw):
        if not kw:
            return
        self.x(f"UPDATE tracks SET {','.join(k + '=?' for k in kw)} WHERE id=?", list(kw.values()) + [tid])
        self.invalidate(tid)

    def mark_played(self, tid):
        now = time.time()
        self.x("UPDATE tracks SET play_count=play_count+1, last_played=? WHERE id=?", (now, tid), False)
        self.x("INSERT INTO history VALUES(?,?)", (tid, now))
        self.invalidate(tid)

    def mark_skipped(self, tid):
        self.x("UPDATE tracks SET skip_count=skip_count+1 WHERE id=?", (tid,))
        self.invalidate(tid)

    def set_favorite(self, tid, fav):
        self.update(tid, favorite=int(bool(fav)))

    def remove_paths(self, paths):
        with self.lock:
            for p in paths:
                self.con.execute("DELETE FROM tracks WHERE path=?", (p,))
            self.con.commit()
        self.invalidate()

    # ── folders
    def folders(self):
        return [r["path"] for r in self.q("SELECT path FROM folders ORDER BY path")]

    def add_folder(self, path):
        self.x("INSERT OR IGNORE INTO folders VALUES(?,?)", (path, time.time()))

    def remove_folder(self, path, purge=True):
        self.x("DELETE FROM folders WHERE path=?", (path,))
        if purge:
            self.x("DELETE FROM tracks WHERE folder=? AND source='local'", (path,))
            self.invalidate()

    def folder_stats(self, path):
        r = self.q("SELECT COUNT(*) n, COALESCE(SUM(duration),0) d, COALESCE(SUM(filesize),0) s FROM tracks WHERE folder=?", (path,))
        return r[0]

    # ── reads
    def ids(self, where="1", args=(), order="artist", limit=None):
        sql = f"SELECT id FROM tracks WHERE {where} ORDER BY {ORDERS.get(order, order)}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [r["id"] for r in self.q(sql, args)]

    def tracks(self, where="1", args=(), order="artist", limit=None):
        sql = f"SELECT * FROM tracks WHERE {where} ORDER BY {ORDERS.get(order, order)}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.q(sql, args)
        for r in rows:
            self._cache[r["id"]] = r
        return rows

    LOCAL = "source='local'"

    def smart(self, kind, limit=200):
        if kind == "recent_played":
            return self.tracks("last_played IS NOT NULL", order="last_played DESC", limit=limit)
        if kind == "most_played":
            return self.tracks("play_count>0", order="play_count DESC, last_played DESC", limit=limit)
        if kind == "recent_added":
            return self.tracks(self.LOCAL, order="added DESC", limit=limit)
        if kind == "favorites":
            return self.tracks("favorite=1", order="title COLLATE NOCASE")
        if kind == "never_played":
            return self.tracks(f"play_count=0 AND {self.LOCAL}", order="RANDOM()", limit=limit)
        if kind == "discovery":
            return self.discovery(limit=min(limit, 60))
        if kind == "lossless":
            return self.tracks("lossless=1", order="artist")
        if kind == "hires":
            return self.tracks("samplerate>48000 OR bitdepth>16", order="artist")
        return []

    def discovery(self, limit=40):
        """Weighted random: favours never/rarely played tracks and forgotten favourites."""
        rows = self.tracks(self.LOCAL, order="id")
        if not rows:
            return []
        now = time.time()

        def w(r):
            base = 1.0 / (1 + r["play_count"]) ** 0.7
            if r["last_played"]:
                base *= min(3.0, 1 + (now - r["last_played"]) / (86400 * 30))
            if r["favorite"]:
                base *= 1.4
            return base
        weights = [w(r) for r in rows]
        picked, seen = [], set()
        for _ in range(limit * 3):
            if len(picked) >= limit or len(seen) >= len(rows):
                break
            r = random.choices(rows, weights)[0]
            if r["id"] not in seen:
                seen.add(r["id"])
                picked.append(r)
        return picked

    def search(self, text, limit=300):
        terms = [t for t in text.strip().split() if t]
        if not terms:
            return []
        where = " AND ".join(["(title LIKE ? OR artist LIKE ? OR album LIKE ? OR albumartist LIKE ? OR genre LIKE ? OR composer LIKE ?)"] * len(terms))
        args = []
        for t in terms:
            args += [f"%{t}%"] * 6
        return self.tracks(where, args, order="play_count DESC, title COLLATE NOCASE", limit=limit)

    def albums(self, where="source='local'", args=(), order="artist"):
        o = {"artist": "aa COLLATE NOCASE, year", "album": "album COLLATE NOCASE", "year": "year DESC",
             "added": "added DESC", "plays": "plays DESC"}.get(order, "aa COLLATE NOCASE")
        return self.q(f"""SELECT album, COALESCE(NULLIF(albumartist,''),NULLIF(artist,''),'Unknown Artist') aa,
                MAX(year) year, COUNT(*) n, SUM(duration) dur, MIN(path) path, MAX(added) added,
                SUM(play_count) plays, MAX(genre) genre, MIN(id) first_id, MAX(lossless) lossless,
                MAX(source) source, MAX(thumb) thumb
                FROM tracks WHERE {where} AND COALESCE(album,'')<>'' GROUP BY lower(aa), lower(album) ORDER BY {o}""", args)

    def album_tracks(self, album, aa):
        return self.tracks("lower(album)=lower(?) AND lower(COALESCE(NULLIF(albumartist,''),NULLIF(artist,''),'Unknown Artist'))=lower(?)",
                           (album, aa), order="disc, track, title COLLATE NOCASE")

    def artists(self):
        return self.q("""SELECT COALESCE(NULLIF(albumartist,''),NULLIF(artist,''),'Unknown Artist') name,
               COUNT(*) n, COUNT(DISTINCT lower(album)) albums, MIN(path) path, SUM(play_count) plays,
               MAX(source) source, MAX(thumb) thumb, MAX(album) album
               FROM tracks WHERE source='local' GROUP BY lower(name) ORDER BY name COLLATE NOCASE""")

    def artist_tracks(self, name, order="plays"):
        return self.tracks("lower(artist)=lower(?) OR lower(albumartist)=lower(?) OR artist LIKE ?",
                           (name, name, f"%{name}%"), order=order)

    def genres(self):
        return self.q("""SELECT COALESCE(NULLIF(genre,''),'Unknown') name, COUNT(*) n, SUM(duration) dur,
                         MIN(path) path FROM tracks WHERE source='local' GROUP BY lower(name) ORDER BY n DESC""")

    def stats(self):
        r = self.q("""SELECT COUNT(*) tracks, COALESCE(SUM(duration),0) dur, COALESCE(SUM(filesize),0) size,
             COUNT(DISTINCT lower(album)) albums,
             COUNT(DISTINCT lower(COALESCE(NULLIF(albumartist,''),artist))) artists,
             COALESCE(SUM(lossless),0) lossless, COALESCE(SUM(play_count),0) plays FROM tracks WHERE source='local'""")[0]
        return r

    # ── playlists
    def playlists(self):
        return self.q("""SELECT p.*, (SELECT COUNT(*) FROM playlist_items i WHERE i.playlist_id=p.id) n
                         FROM playlists p ORDER BY p.name COLLATE NOCASE""")

    def create_playlist(self, name, ids=(), description=""):
        cur = self.x("INSERT INTO playlists(name,created,description) VALUES(?,?,?)", (name, time.time(), description))
        pid = cur.lastrowid
        self.add_to_playlist(pid, ids)
        return pid

    def playlist(self, pid):
        r = self.q("SELECT * FROM playlists WHERE id=?", (pid,))
        return r[0] if r else None

    def playlist_by_origin(self, origin):
        r = self.q("SELECT * FROM playlists WHERE origin=?", (origin,))
        return r[0] if r else None

    def save_remote_playlist(self, info, ids):
        """Create or re-sync a playlist that mirrors a Spotify / YouTube playlist. Returns (pid, created)."""
        ex = self.playlist_by_origin(info["origin"])
        if ex:
            pid = ex["id"]
            self.set_playlist_order(pid, ids)
            self.x("UPDATE playlists SET link=?, thumb=?, synced=? WHERE id=?", (info.get("link"), info.get("thumb"), time.time(), pid))
            return pid, False
        src = "Spotify" if info["origin"].startswith("spotify") else "YouTube"
        pid = self.create_playlist(info["name"], ids, f"Imported from {src}")
        self.x("UPDATE playlists SET origin=?, link=?, thumb=?, synced=? WHERE id=?",
               (info["origin"], info.get("link"), info.get("thumb"), time.time(), pid))
        return pid, True

    def replace_track(self, old_id, new_id):
        """Point playlists at a downloaded local copy instead of the stream entry."""
        if old_id and new_id and old_id != new_id:
            self.x("UPDATE playlist_items SET track_id=? WHERE track_id=?", (new_id, old_id))

    def rename_playlist(self, pid, name):
        self.x("UPDATE playlists SET name=? WHERE id=?", (name, pid))

    def delete_playlist(self, pid):
        self.x("DELETE FROM playlist_items WHERE playlist_id=?", (pid,))
        self.x("DELETE FROM playlists WHERE id=?", (pid,))

    def add_to_playlist(self, pid, ids):
        with self.lock:
            n = self.con.execute("SELECT COALESCE(MAX(pos),-1)+1 FROM playlist_items WHERE playlist_id=?", (pid,)).fetchone()[0]
            self.con.executemany("INSERT INTO playlist_items VALUES(?,?,?)", [(pid, t, n + i) for i, t in enumerate(ids)])
            self.con.commit()

    def playlist_tracks(self, pid):
        ids = [r["track_id"] for r in self.q("SELECT track_id FROM playlist_items WHERE playlist_id=? ORDER BY pos", (pid,))]
        return self.get_many(ids)

    def set_playlist_order(self, pid, ids):
        with self.lock:
            self.con.execute("DELETE FROM playlist_items WHERE playlist_id=?", (pid,))
            self.con.executemany("INSERT INTO playlist_items VALUES(?,?,?)", [(pid, t, i) for i, t in enumerate(ids)])
            self.con.commit()

    def remove_from_playlist(self, pid, positions):
        ids = [t["id"] for t in self.playlist_tracks(pid)]
        keep = [t for i, t in enumerate(ids) if i not in set(positions)]
        self.set_playlist_order(pid, keep)

    # ── streaming entries
    def add_stream(self, item: dict):
        d = {"path": f"{item['source']}:{item['id']}", "source": item["source"], "url": item.get("url"),
             "thumb": item.get("thumb"), "title": item.get("title"), "artist": item.get("artist"),
             "album": item.get("album") or "", "albumartist": "", "duration": item.get("duration") or 0,
             "codec": "stream", "genre": item.get("genre") or "", "has_art": int(bool(item.get("thumb")))}
        return self.upsert(d)
