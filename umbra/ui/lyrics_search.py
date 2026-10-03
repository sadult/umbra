"""Search LRCLIB for lyrics by free text, preview candidates and attach one to the track."""
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QStyledItemDelegate,
                               QAbstractItemView, QFrame)

from ..library.lyrics import lrclib_search, save_lyrics
from .context import ctx
from .widgets import Badge, GlassDialog, PillButton, SearchField, Toggle, fmt_time, font, label


class _Sig(QObject):
    done = Signal(int, object, str)


class _Delegate(QStyledItemDelegate):
    def sizeHint(self, opt, idx):
        from PySide6.QtCore import QSize
        return QSize(opt.rect.width(), 52)

    def paint(self, p, opt, idx):
        d = idx.data(Qt.UserRole)
        r = opt.rect.adjusted(2, 2, -2, -2)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        from PySide6.QtWidgets import QStyle
        if opt.state & QStyle.State_Selected:
            p.setPen(Qt.NoPen)
            p.setBrush(ctx.theme.acc(40))
            p.drawRoundedRect(r, 10, 10)
        elif opt.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 12))
            p.drawRoundedRect(r, 10, 10)
        kind = "SYNCED" if d["synced"] else ("INSTRUMENTAL" if d["instrumental"] else "PLAIN")
        p.setFont(font(7, QFont.Bold, 1, mono=True))
        fm = QFontMetrics(p.font())
        bw = fm.horizontalAdvance(kind) + 14
        br = r.adjusted(r.width() - bw - 10, 16, -10, -16)
        p.setPen(ctx.theme.acc(220) if d["synced"] else QColor(255, 255, 255, 140))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(br, 5, 5)
        p.drawText(br, Qt.AlignCenter, kind)
        w = r.width() - bw - 40
        p.setFont(font(9.6, QFont.DemiBold))
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(r.adjusted(12, 6, 0, 0).x(), r.top() + 22, QFontMetrics(p.font()).elidedText(d["title"], Qt.ElideRight, w))
        p.setFont(font(8.4))
        p.setPen(QColor(255, 255, 255, 120))
        sub = " · ".join(x for x in (d["artist"], d["album"], fmt_time(d["duration"]) if d["duration"] else "") if x)
        p.drawText(r.left() + 12, r.top() + 40, QFontMetrics(p.font()).elidedText(sub, Qt.ElideRight, w))
        p.restore()


class LyricsSearchDialog(GlassDialog):
    def __init__(self, parent, track):
        super().__init__(parent, "Search lyrics online", 860, 560)
        self.t = track
        self._tok = 0
        self.sig = _Sig()
        self.sig.done.connect(self._show)
        row = QHBoxLayout()
        q = " ".join(x for x in (track.get("artist"), track.get("title")) if x)
        self.field = SearchField("Artist and song title…", hint="Enter")
        self.field.setText(q)
        self.field.returnPressed.connect(self.search)
        go = PillButton("Search", "search", primary=True)
        go.clicked.connect(self.search)
        row.addWidget(self.field, 1)
        row.addWidget(go)
        self.body.addLayout(row)
        self.status = label("", 8.8, alpha=130)
        self.body.addWidget(self.status)
        mid = QHBoxLayout()
        mid.setSpacing(12)
        self.list = QListWidget()
        self.list.setItemDelegate(_Delegate(self.list))
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.currentItemChanged.connect(self._preview)
        self.list.itemDoubleClicked.connect(lambda _i: self.add())
        mid.addWidget(self.list, 5)
        self.prev = QPlainTextEdit()
        self.prev.setReadOnly(True)
        self.prev.setFont(font(9))
        mid.addWidget(self.prev, 4)
        self.body.addLayout(mid, 1)
        foot = QHBoxLayout()
        local = track.get("source", "local") == "local"
        self.embed = Toggle(False)
        self.embed.setVisible(local)
        foot.addWidget(self.embed)
        el = label("Embed in the file's tags instead of a side-car .lrc", 8.6, alpha=150)
        el.setVisible(local)
        foot.addWidget(el)
        foot.addStretch()
        c = PillButton("Cancel")
        c.clicked.connect(self.reject)
        self.add_btn = PillButton("Add lyrics", "plus", primary=True)
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.add)
        foot.addWidget(c)
        foot.addWidget(self.add_btn)
        self.body.addLayout(foot)
        self.search()

    def search(self):
        q = self.field.text().strip()
        if not q:
            return
        self._tok += 1
        tok = self._tok
        self.status.setText("Searching LRCLIB…")
        self.list.clear()
        self.prev.clear()
        self.add_btn.setEnabled(False)

        def run():
            try:
                res, err = lrclib_search(q), ""
            except Exception as e:
                res, err = [], str(e)
            self.sig.done.emit(tok, res, err)
        threading.Thread(target=run, daemon=True).start()

    def _show(self, tok, res, err):
        if tok != self._tok:
            return
        if err:
            self.status.setText("Couldn't reach LRCLIB — check your connection.  (" + err[:80] + ")")
            return
        self.status.setText(f"{len(res)} result{'s' if len(res) != 1 else ''} — pick one to preview, then Add."
                            if res else "Nothing found. Try fewer words, or just the song title.")
        for d in res:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, d)
            self.list.addItem(it)
        if res:
            self.list.setCurrentRow(0)

    def _preview(self, it, _prev=None):
        d = it.data(Qt.UserRole) if it else None
        self.prev.setPlainText(("(instrumental)" if d["instrumental"] else (d["synced"] or d["plain"])) if d else "")
        self.add_btn.setEnabled(bool(d) and not d["instrumental"])

    def add(self):
        it = self.list.currentItem()
        if not it:
            return
        d = it.data(Qt.UserRole)
        text = d["synced"] or d["plain"]
        if not text:
            return
        where = save_lyrics(self.t, text, embed=self.embed.isChecked())
        ctx.lyrics.request(self.t)
        ctx.toast(f"Lyrics added  ·  {where}", "lyrics")
        self.accept()


def search_lyrics(parent, track):
    if track:
        LyricsSearchDialog(parent, track).exec()
