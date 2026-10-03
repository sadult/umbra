"""Tag Editor — single & batch editing of every common field, artwork and lyrics."""
import json
import os
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal, QObject
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QGuiApplication
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QPlainTextEdit,
                               QStackedWidget, QVBoxLayout, QWidget, QLineEdit)

from ..library.lyrics import lrclib_fetch, parse_lrc
from ..library.tags import (filename_from_tags, find_folder_art, format_from_filename, get_embedded_art, read_tags,
                            write_tags)
from . import icons
from .context import ctx
from .widgets import (Badge, Caption, ChipButton, GlassDialog, IconButton, PillButton, Segmented, TextField, ask_text,
                      font, glass_menu, label)
from .actions import _act

FIELDS = [("title", "Title"), ("artist", "Artist"), ("albumartist", "Album Artist"), ("album", "Album"),
          ("genre", "Genre"), ("year", "Year"), ("track", "Track"), ("tracktotal", "of"), ("disc", "Disc"),
          ("disctotal", "of"), ("composer", "Composer"), ("comment", "Comment")]
PNG_MAGIC = b"\x89PNG"
MULTI = "‹ multiple values — leave to keep ›"


class ArtDrop(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(260, 260)
        self.setAcceptDrops(True)
        self.img = None
        self.data = None
        self.mixed = False
        self.h = False
        self.setCursor(Qt.PointingHandCursor)

    def set_data(self, data, mixed=False):
        self.data = data
        self.mixed = mixed
        self.img = QImage.fromData(data) if data else None
        self.update()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            self.h = True
            self.update()
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.h = False
        self.update()

    def dropEvent(self, e):
        self.h = False
        md = e.mimeData()
        if md.hasUrls():
            p = md.urls()[0].toLocalFile()
            if p and os.path.isfile(p):
                self.set_data(Path(p).read_bytes())
                self.changed.emit()
        elif md.hasImage():
            self._from_qimage(QImage(md.imageData()))

    def _from_qimage(self, img):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "JPG", 94)
        self.set_data(bytes(ba))
        self.changed.emit()

    def mouseReleaseEvent(self, e):
        fn, _ = QFileDialog.getOpenFileName(self, "Choose artwork", "", "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if fn:
            self.set_data(Path(fn).read_bytes())
            self.changed.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        from .art import rounded
        if self.img is not None and not self.img.isNull():
            p.drawPixmap(r.toRect(), rounded(self.img, int(r.width()), 16))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 60), 1.2, Qt.DashLine))
            p.setBrush(QColor(255, 255, 255, 8))
            p.drawRoundedRect(r, 16, 16)
            icons.draw(p, "image", QRectF(r.center().x() - 22, r.center().y() - 40, 44, 44), QColor(255, 255, 255, 110))
            p.setFont(font(9, QFont.Medium))
            p.setPen(QColor(255, 255, 255, 140))
            p.drawText(QRectF(r.left(), r.center().y() + 12, r.width(), 40), Qt.AlignCenter | Qt.TextWordWrap,
                       "Mixed artwork — drop to replace all" if self.mixed else "Drop an image or click to choose")
        if self.h:
            p.setPen(QPen(ctx.theme.accent, 2))
            p.setBrush(ctx.theme.acc(30))
            p.drawRoundedRect(r, 16, 16)


class _Sig(QObject):
    done = Signal(object, object)


class TagEditor(GlassDialog):
    def __init__(self, parent, tracks):
        super().__init__(parent, "Tag Editor", 1000, 700)
        self.tracks = [t for t in tracks if t.get("source", "local") == "local" and os.path.exists(t["path"])]
        self.n = len(self.tracks)
        self.tags = [read_tags(t["path"]) for t in self.tracks]
        self.dirty = set()
        self.per_track = [dict() for _ in self.tracks]
        self.art_action = None   # None keep | bytes | 'remove'
        self._sig = _Sig()
        self._sig.done.connect(self._async_done)
        self.title.setText("Tag Editor" + (f"  ·  {self.n} tracks" if self.n > 1 else ""))
        main = QHBoxLayout()
        main.setSpacing(22)
        # ── left: artwork
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(Caption("Artwork"))
        self.art = ArtDrop()
        self.art.changed.connect(self._art_changed)
        left.addWidget(self.art)
        self.art_info = label("", 8.5, alpha=120)
        left.addWidget(self.art_info)
        grid = QGridLayout()
        grid.setSpacing(6)
        btns = [("Choose…", "image", self.art.mouseReleaseEvent), ("Paste", "download", self._paste),
                ("Find online", "globe", self._online_art), ("From folder", "folder", self._folder_art),
                ("Export", "external", self._export_art), ("Remove", "trash", self._remove_art)]
        for i, (t, ic, fn) in enumerate(btns):
            b = ChipButton(t, ic)
            b.clicked.connect(lambda _=False, f=fn: f(None) if f == self.art.mouseReleaseEvent else f())
            grid.addWidget(b, i // 2, i % 2)
        left.addLayout(grid)
        left.addStretch()
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(270)
        main.addWidget(lw)
        # ── right
        right = QVBoxLayout()
        right.setSpacing(12)
        top = QHBoxLayout()
        self.tabs = Segmented([("details", "Details"), ("lyrics", "Lyrics"), ("file", "File")], "details")
        self.tabs.changed.connect(lambda k: self.stack.setCurrentIndex(["details", "lyrics", "file"].index(k)))
        top.addWidget(self.tabs)
        top.addStretch()
        self.tools = PillButton("Tools", "sliders")
        self.tools.clicked.connect(self._tools_menu)
        top.addWidget(self.tools)
        right.addLayout(top)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        # details
        dw = QWidget()
        g = QGridLayout(dw)
        g.setContentsMargins(0, 4, 0, 0)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        self.ed = {}
        genres = sorted({r["name"] for r in ctx.lib.genres() if r["name"] != "Unknown"})
        row = 0

        def add(key, lab, r, c, span=5):
            g.addWidget(label(lab, 8.5, QFont.DemiBold, alpha=140), r, c)
            if key == "genre":
                w = QComboBox()
                w.setEditable(True)
                w.addItems([""] + genres)
                e = w.lineEdit()
            else:
                w = TextField()
                e = w
            e.textEdited.connect(lambda _=None, k=key: self.dirty.add(k))
            self.ed[key] = e
            g.addWidget(w, r, c + 1, 1, span)
        for key in ("title", "artist", "albumartist", "album", "genre", "composer"):
            add(key, dict(FIELDS)[key], row, 0)
            row += 1
        add("year", "Year", row, 0, 1)
        add("track", "Track", row, 2, 1)
        g.addWidget(label("of", 8.5, alpha=120), row, 4)
        self.ed_tt = TextField()
        self.ed_tt.textEdited.connect(lambda _: self.dirty.add("tracktotal"))
        self.ed["tracktotal"] = self.ed_tt
        g.addWidget(self.ed_tt, row, 5)
        row += 1
        add("disc", "Disc", row, 0, 1)
        g.addWidget(label("of", 8.5, alpha=120), row, 2)
        self.ed_dt = TextField()
        self.ed_dt.textEdited.connect(lambda _: self.dirty.add("disctotal"))
        self.ed["disctotal"] = self.ed_dt
        g.addWidget(self.ed_dt, row, 3)
        row += 1
        g.addWidget(label("Comment", 8.5, QFont.DemiBold, alpha=140), row, 0, Qt.AlignTop)
        self.comment = QPlainTextEdit()
        self.comment.setFixedHeight(80)
        self.comment.textChanged.connect(lambda: self.comment.hasFocus() and self.dirty.add("comment"))
        g.addWidget(self.comment, row, 1, 1, 5)
        row += 1
        g.setRowStretch(row, 1)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        g.setColumnStretch(5, 1)
        self.stack.addWidget(dw)
        # lyrics
        lw2 = QWidget()
        ll = QVBoxLayout(lw2)
        ll.setContentsMargins(0, 4, 0, 0)
        lr = QHBoxLayout()
        self.lyr_badge = Badge("")
        lr.addWidget(self.lyr_badge)
        lr.addStretch()
        for t, ic, fn in (("Fetch LRCLIB", "cloud", self._fetch_lyrics), ("Import .lrc", "download", self._import_lrc),
                          ("Save .lrc", "external", self._save_lrc), ("Clear", "trash", lambda: (self.lyrics.clear(), self.dirty.add("lyrics")))):
            b = ChipButton(t, ic)
            b.clicked.connect(fn)
            lr.addWidget(b)
        ll.addLayout(lr)
        self.lyrics = QPlainTextEdit()
        self.lyrics.setFont(font(10, mono=True))
        self.lyrics.setPlaceholderText("Plain text or LRC:\n[00:12.40] First line\n[00:17.85] Second line")
        self.lyrics.textChanged.connect(self._lyr_changed)
        ll.addWidget(self.lyrics, 1)
        self.stack.addWidget(lw2)
        # file
        fw = QWidget()
        fl = QVBoxLayout(fw)
        fl.setContentsMargins(0, 4, 0, 0)
        self.file_info = QPlainTextEdit()
        self.file_info.setReadOnly(True)
        self.file_info.setFont(font(9, mono=True))
        fl.addWidget(self.file_info)
        self.stack.addWidget(fw)
        main.addLayout(right, 1)
        self.body.addLayout(main, 1)
        # footer
        foot = QHBoxLayout()
        self.status = label("", 8.6, alpha=130)
        foot.addWidget(self.status, 1)
        cancel = PillButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.save_btn = PillButton("Save changes", "check", primary=True)
        self.save_btn.clicked.connect(self._save)
        foot.addWidget(cancel)
        foot.addWidget(self.save_btn)
        self.body.addLayout(foot)
        self._populate()

    # ── populate
    def _populate(self):
        for key, _ in FIELDS:
            vals = {str(t.get(key) or "") for t in self.tags}
            vals = {("" if v == "0" else v) for v in vals}
            if key == "comment":
                if len(vals) == 1:
                    self.comment.setPlainText(next(iter(vals)))
                else:
                    self.comment.setPlaceholderText(MULTI)
                continue
            e = self.ed[key]
            if len(vals) == 1:
                e.setText(next(iter(vals)))
            else:
                e.setText("")
                e.setPlaceholderText(MULTI)
        lv = {t.get("lyrics") or "" for t in self.tags}
        self._lock_lyr = True
        if len(lv) == 1:
            self.lyrics.setPlainText(next(iter(lv)))
        else:
            self.lyrics.setPlaceholderText(MULTI)
        self._lock_lyr = False
        self._lyr_badge()
        arts = [get_embedded_art(t["path"]) for t in self.tracks[:50]]
        uniq = {a for a in arts if a}
        if len(uniq) == 1 and all(arts):
            self.art.set_data(arts[0])
        elif not uniq:
            self.art.set_data(None)
        else:
            self.art.set_data(arts[0], mixed=False) if len(uniq) == 1 else self.art.set_data(None, mixed=True)
        self._art_info()
        t0, g0 = self.tracks[0], self.tags[0]
        lines = []
        for t, g in list(zip(self.tracks, self.tags))[:30]:
            size = os.path.getsize(t["path"]) / 1e6
            lines.append(f"{t['path']}\n  {g['codec'].upper()}  {g['bitdepth'] or '-'} bit  {g['samplerate']} Hz  "
                         f"{g['channels']} ch  {g['bitrate']} kbps  {g['duration']:.2f}s  {size:.1f} MB"
                         f"  RG {g['rg_track'] if g['rg_track'] is not None else '-'} dB\n")
        if self.n > 30:
            lines.append(f"… and {self.n - 30} more files")
        self.file_info.setPlainText("\n".join(lines))
        self.status.setText(os.path.dirname(t0["path"]) if self.n == 1 else f"{self.n} files selected — only edited fields are written")

    def _lyr_badge(self):
        txt = self.lyrics.toPlainText()
        if not txt.strip():
            self.lyr_badge.setText("NO LYRICS")
        elif parse_lrc(txt):
            self.lyr_badge.setText(f"SYNCED · {len(parse_lrc(txt))} LINES", True)
        else:
            self.lyr_badge.setText("PLAIN TEXT", False)

    def _lyr_changed(self):
        if not getattr(self, "_lock_lyr", False):
            self.dirty.add("lyrics")
        self._lyr_badge()

    def _art_info(self):
        d = self.art.data
        if self.art_action == "remove":
            self.art_info.setText("Artwork will be removed")
        elif d:
            img = self.art.img
            kind = "PNG" if d[:4] == PNG_MAGIC else "JPEG"
            self.art_info.setText(f"{img.width()} × {img.height()}  ·  {len(d) / 1024:.0f} KB  ·  {kind}"
                                  + ("  ·  modified" if self.art_action else ""))
        else:
            self.art_info.setText("No embedded artwork")

    def _art_changed(self):
        self.art_action = self.art.data
        self._art_info()

    # ── artwork actions
    def _paste(self):
        cb = QGuiApplication.clipboard()
        img = cb.image()
        if not img.isNull():
            self.art._from_qimage(img)
        elif cb.mimeData().hasUrls():
            p = cb.mimeData().urls()[0].toLocalFile()
            if os.path.isfile(p):
                self.art.set_data(Path(p).read_bytes())
                self._art_changed()

    def _folder_art(self):
        d = find_folder_art(self.tracks[0]["path"], ctx.settings["folder_art_names"])
        if d:
            self.art.set_data(d)
            self._art_changed()
        else:
            ctx.toast("No image found in the folder", "info")

    def _online_art(self):
        g = self.tags[0]
        artist = self.ed["albumartist"].text() or self.ed["artist"].text() or g.get("artist")
        album = self.ed["album"].text() or g.get("album") or self.ed["title"].text()
        self.art_info.setText("Searching iTunes artwork…")

        def run():
            try:
                q = urllib.parse.urlencode({"term": f"{artist} {album}", "entity": "album", "limit": 1})
                with urllib.request.urlopen("https://itunes.apple.com/search?" + q, timeout=10) as r:
                    res = json.loads(r.read().decode())
                url = res["results"][0]["artworkUrl100"].replace("100x100bb", "1200x1200bb")
                with urllib.request.urlopen(url, timeout=15) as r:
                    data = r.read()
                self._sig.done.emit("art", data)
            except Exception as e:
                self._sig.done.emit("art", None)
        threading.Thread(target=run, daemon=True).start()

    def _export_art(self):
        if not self.art.data:
            return
        ext = "png" if self.art.data[:4] == PNG_MAGIC else "jpg"
        fn, _ = QFileDialog.getSaveFileName(self, "Export artwork", f"cover.{ext}")
        if fn:
            Path(fn).write_bytes(self.art.data)

    def _remove_art(self):
        self.art.set_data(None)
        self.art_action = "remove"
        self._art_info()

    # ── lyrics actions
    def _fetch_lyrics(self):
        t = dict(self.tracks[0])
        t.update(artist=self.ed["artist"].text() or t.get("artist"), title=self.ed["title"].text() or t.get("title"),
                 album=self.ed["album"].text() or t.get("album"))
        self.lyr_badge.setText("SEARCHING…")

        def run():
            self._sig.done.emit("lyrics", lrclib_fetch(t))
        threading.Thread(target=run, daemon=True).start()

    def _import_lrc(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Import lyrics", os.path.dirname(self.tracks[0]["path"]), "Lyrics (*.lrc *.txt)")
        if fn:
            self.lyrics.setPlainText(Path(fn).read_text("utf-8", errors="ignore"))

    def _save_lrc(self):
        txt = self.lyrics.toPlainText()
        if txt.strip():
            p = Path(self.tracks[0]["path"]).with_suffix(".lrc")
            p.write_text(txt, "utf-8")
            ctx.toast(f"Saved {p.name}", "lyrics")

    def _async_done(self, kind, data):
        if kind == "art":
            if data:
                self.art.set_data(data)
                self._art_changed()
            else:
                self.art_info.setText("No artwork found online")
        elif kind == "lyrics":
            if data and (data.get("synced") or data.get("plain")):
                self.lyrics.setPlainText(data.get("synced") or data.get("plain"))
            else:
                self._lyr_badge()
                ctx.toast("No lyrics found on LRCLIB", "info")

    # ── tools
    def _tools_menu(self):
        m = glass_menu(self)
        _act(m, "Auto-number tracks (current order)", "songs", self._autonum)
        _act(m, "Title Case all text fields", "edit", self._titlecase)
        _act(m, "Copy Artist → Album Artist", "artists", self._copy_aa)
        m.addSeparator()
        _act(m, "Tags from filename…", "download", self._from_filename)
        _act(m, "Rename files from tags…", "external", self._rename)
        m.exec(self.tools.mapToGlobal(self.tools.rect().bottomLeft()))

    def _autonum(self):
        for i, pt in enumerate(self.per_track):
            pt["track"] = i + 1
            pt["tracktotal"] = self.n
        self.ed["track"].setPlaceholderText("auto 1…%d" % self.n)
        self.ed["track"].setText("" if self.n > 1 else "1")
        self.ed["tracktotal"].setText(str(self.n))
        self.dirty.add("tracktotal")
        ctx.toast(f"Numbered {self.n} tracks", "songs")

    def _titlecase(self):
        import re
        small = {"a", "an", "the", "of", "in", "on", "and", "or", "to", "for", "at", "by"}

        def tc(s):
            words = s.split(" ")
            return " ".join(w if (w.isupper() and len(w) > 1) else (w.lower() if (i and w.lower() in small) else w[:1].upper() + w[1:].lower())
                            for i, w in enumerate(words))
        for k in ("title", "artist", "albumartist", "album", "genre", "composer"):
            e = self.ed[k]
            if e.text():
                e.setText(tc(e.text()))
                self.dirty.add(k)
        if self.n > 1:
            for pt, g in zip(self.per_track, self.tags):
                pt["title"] = tc(g.get("title") or "")

    def _copy_aa(self):
        for pt, g in zip(self.per_track, self.tags):
            pt["albumartist"] = self.ed["artist"].text() or g.get("artist") or ""
        ctx.toast("Album Artist will be set from Artist", "artists")

    def _from_filename(self):
        pat = ask_text(self, "Tags from filename", "Pattern  (%track% %artist% %title% %album% %year% %disc%)",
                       "%track% - %artist% - %title%")
        if not pat:
            return
        ok = 0
        for pt, t in zip(self.per_track, self.tracks):
            d = format_from_filename(t["path"], pat)
            if d:
                pt.update(d)
                ok += 1
        if self.n == 1 and ok:
            for k, v in self.per_track[0].items():
                if k in self.ed:
                    self.ed[k].setText(str(v))
                    self.dirty.add(k)
        ctx.toast(f"Parsed {ok}/{self.n} filenames", "tag")

    def _rename(self):
        pat = ask_text(self, "Rename files", "Pattern  (%track% %artist% %title% %album% %year%)", "%track% - %title%")
        if not pat:
            return
        self._rename_pattern = pat
        ctx.toast("Files will be renamed on save", "external")

    # ── save
    def _collect(self):
        v = {}
        for k in self.dirty:
            if k == "comment":
                v[k] = self.comment.toPlainText()
            elif k == "lyrics":
                v[k] = self.lyrics.toPlainText()
            elif k in self.ed:
                txt = self.ed[k].text().strip()
                v[k] = int(txt) if k in ("year", "track", "tracktotal", "disc", "disctotal") and txt.isdigit() else (0 if k in ("year", "track", "tracktotal", "disc", "disctotal") else txt)
        return v

    def _save(self):
        base = self._collect()
        art = self.art_action
        errors = 0
        self.save_btn.setEnabled(False)
        for i, (t, pt) in enumerate(zip(self.tracks, self.per_track)):
            vals = dict(base)
            vals.update({k: v for k, v in pt.items() if k not in base or k in ("track", "tracktotal") and not self.ed["track"].text()})
            path = t["path"]
            try:
                if vals or art is not None:
                    write_tags(path, vals, art)
                pat = getattr(self, "_rename_pattern", None)
                if pat:
                    tg = read_tags(path)
                    newname = filename_from_tags(tg, pat) + Path(path).suffix
                    newp = str(Path(path).with_name(newname))
                    if newp != path and not os.path.exists(newp):
                        os.rename(path, newp)
                        lrc = Path(path).with_suffix(".lrc")
                        if lrc.exists():
                            lrc.rename(Path(newp).with_suffix(".lrc"))
                        ctx.lib.x("UPDATE tracks SET path=? WHERE id=?", (newp, t["id"]))
                        path = newp
                d = read_tags(path)
                d.pop("lyrics", None)
                st = os.stat(path)
                d.update(path=path, filesize=st.st_size, mtime=st.st_mtime)
                ctx.lib.upsert(d)
                ctx.art.invalidate(t)
                ctx.art.invalidate(ctx.lib.get(t["id"]) or t)
            except Exception as e:
                errors += 1
                print("tag write failed:", path, e)
            if i % 5 == 0:
                self.status.setText(f"Writing {i + 1}/{self.n}…")
                QApplication.processEvents()
        ctx.lib.invalidate()
        if "lyrics" in self.dirty:
            for t in self.tracks:
                ctx.lyrics.forget(t)
        ctx.win.library_changed()
        ctx.toast(f"Saved {self.n - errors} file{'s' if self.n - errors != 1 else ''}" + (f" · {errors} failed" if errors else ""), "check")
        self.accept()
