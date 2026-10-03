"""High-density, hand-painted track list (Spotify × foobar2000)."""
import math
import time

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget

from . import icons
from .actions import track_menu
from .context import ctx
from .widgets import fmt_time, font

COLS = [("num", "#", 40, 0), ("title", "TITLE", 0, 0.46), ("album", "ALBUM", 0, 0.30),
        ("added", "ADDED", 84, 0), ("plays", "PLAYS", 58, 0), ("fav", "", 36, 0), ("dur", "TIME", 58, 0)]


def col_rects(w, show_album=True):
    fixed = sum(c[2] for c in COLS if c[2]) + 12
    flex = max(0, w - fixed - 52)
    cols = COLS if show_album else [c for c in COLS if c[0] != "album"]
    tot = sum(c[3] for c in cols)
    x = 12
    out = {}
    for key, _, fw, fr in cols:
        cw = fw if fw else (flex * fr / tot) + (52 if key == "title" else 0)
        out[key] = (x, cw)
        x += cw
    return out


class TrackModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.rows = []

    def set_tracks(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid():
            return None
        if role == Qt.UserRole:
            return self.rows[idx.row()]
        if role == Qt.DisplayRole:
            return self.rows[idx.row()].get("title")
        return None

    def refresh_row(self, tid):
        for i, r in enumerate(self.rows):
            if r["id"] == tid:
                self.rows[i] = ctx.lib.get(tid) or r
                ix = self.index(i)
                self.dataChanged.emit(ix, ix)


def ago(ts):
    if not ts:
        return ""
    d = time.time() - ts
    if d < 3600:
        return f"{max(1, int(d // 60))} min"
    if d < 86400:
        return f"{int(d // 3600)} h"
    if d < 86400 * 30:
        return f"{int(d // 86400)} d"
    return time.strftime("%b %Y", time.localtime(ts))


class TrackDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.v = view
        self.f_title = font(9.8, QFont.DemiBold)
        self.f_sub = font(8.6)
        self.f_num = font(8.6, QFont.Medium)

    def sizeHint(self, opt, idx):
        return QSize(opt.rect.width(), 56)

    def paint(self, p: QPainter, opt, idx):
        t = idx.data(Qt.UserRole)
        if not t:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        th = ctx.theme
        r = QRectF(opt.rect).adjusted(4, 2, -4, -2)
        hover = idx.row() == self.v.hover_row
        sel = bool(opt.state & QStyle.State_Selected)
        cur = ctx.player.current
        playing = bool(cur and cur.get("id") == t["id"])
        if sel or hover or playing:
            a = 26 if sel else (16 if hover else 0)
            if playing:
                g = th.acc(22)
                p.setBrush(g)
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(r, 12, 12)
            if a:
                p.setBrush(QColor(255, 255, 255, a))
                p.setPen(QPen(QColor(255, 255, 255, 24 if sel else 10), 1))
                p.drawRoundedRect(r, 12, 12)
        cols = col_rects(r.width(), self.v.show_album)
        ox, cy = r.left(), r.center().y()
        dim = QColor(255, 255, 255, 125)
        txt = QColor(255, 255, 255, 238)
        # number / eq bars / play glyph
        x, w = cols["num"]
        nr = QRectF(ox + x, r.top(), w, r.height())
        if playing:
            self._bars(p, nr, th.accent, ctx.player.engine.state == "playing")
        elif hover:
            icons.draw(p, "play", QRectF(nr.center().x() - 8, cy - 8, 16, 16), txt)
        else:
            p.setFont(self.f_num)
            p.setPen(dim)
            n = t.get("track") if self.v.number_mode == "track" and t.get("track") else idx.row() + 1
            p.drawText(nr, Qt.AlignCenter, str(n))
        # cover + title + artist
        x, w = cols["title"]
        cs = 40
        if self.v.show_cover:
            pm = ctx.art.get(t, cs, 8)
            p.drawPixmap(QRectF(ox + x, cy - cs / 2, cs, cs).toRect(), pm)
            tx = ox + x + cs + 12
        else:
            tx = ox + x + 4
        tw = ox + x + w - tx - 8
        p.setFont(self.f_title)
        p.setPen(th.accent.lighter(110) if playing else txt)
        fm = QFontMetrics(self.f_title)
        title = fm.elidedText(t.get("title") or "Untitled", Qt.ElideRight, int(tw))
        p.drawText(QRectF(tx, cy - 19, tw, 20), Qt.AlignLeft | Qt.AlignVCenter, title)
        p.setFont(self.f_sub)
        p.setPen(dim)
        sub = t.get("artist") or "Unknown Artist"
        badge = ""
        if t.get("source", "local") != "local":
            badge = {"youtube": "YT", "spotify": "SP"}.get(t["source"], "WEB")
        elif t.get("lossless") and (t.get("bitdepth", 0) > 16 or t.get("samplerate", 0) > 48000):
            badge = "HI-RES"
        elif t.get("lossless"):
            badge = "LOSSLESS" if self.v.width() > 900 else ""
        bx = tx
        if badge:
            bf = font(6.4, QFont.Bold, 0.6)
            bw = QFontMetrics(bf).horizontalAdvance(badge) + 10
            br = QRectF(tx, cy + 4, bw, 14)
            p.setPen(QPen(th.acc(120) if badge == "HI-RES" else QColor(255, 255, 255, 60), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(br, 4, 4)
            p.setFont(bf)
            p.setPen(th.accent if badge == "HI-RES" else QColor(255, 255, 255, 150))
            p.drawText(br, Qt.AlignCenter, badge)
            bx = tx + bw + 7
            p.setFont(self.f_sub)
            p.setPen(dim)
        p.drawText(QRectF(bx, cy + 1, tw - (bx - tx), 20), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(self.f_sub).elidedText(sub, Qt.ElideRight, int(tw - (bx - tx))))
        # album
        if "album" in cols:
            x, w = cols["album"]
            p.setPen(dim)
            p.drawText(QRectF(ox + x, r.top(), w - 10, r.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(self.f_sub).elidedText(t.get("album") or "", Qt.ElideRight, int(w - 14)))
        x, w = cols["added"]
        p.setPen(QColor(255, 255, 255, 90))
        p.drawText(QRectF(ox + x, r.top(), w, r.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   ago(t.get("last_played") if self.v.date_mode == "played" else t.get("added")))
        x, w = cols["plays"]
        pc = t.get("play_count") or 0
        if t.get("source", "local") != "local" and ctx.downloads is not None:
            st = ctx.downloads.state(t)
            ir = QRectF(ox + x + w - 30, cy - 8, 16, 16)
            if st == "done":
                icons.draw(p, "check", ir, th.accent)
            elif isinstance(st, float):
                p.setPen(QPen(QColor(255, 255, 255, 40), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(ir.center(), 7, 7)
                p.setPen(QPen(th.accent, 2, Qt.SolidLine, Qt.RoundCap))
                p.drawArc(ir.adjusted(1, 1, -1, -1).toRect(), 90 * 16, -int(360 * 16 * max(0.04, st)))
            else:
                icons.draw(p, "download", ir, QColor(255, 255, 255, 200 if hover else 110))
        elif pc:
            p.drawText(QRectF(ox + x, r.top(), w - 12, r.height()), Qt.AlignRight | Qt.AlignVCenter, str(pc))
        x, w = cols["fav"]
        fav = t.get("favorite")
        if fav or hover:
            icons.draw(p, "heart_fill" if fav else "heart", QRectF(ox + x + (w - 16) / 2, cy - 8, 16, 16),
                       th.accent if fav else QColor(255, 255, 255, 140))
        x, w = cols["dur"]
        p.setFont(self.f_num)
        p.setPen(dim)
        p.drawText(QRectF(ox + x, r.top(), w - 8, r.height()), Qt.AlignRight | Qt.AlignVCenter, fmt_time(t.get("duration")))
        p.restore()

    def _bars(self, p, r, col, animate):
        t = time.time() if animate else 0
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        bw, gap = 3, 2.5
        x0 = r.center().x() - (3 * bw + 2 * gap) / 2
        for i in range(3):
            h = 4 + (10 * (0.5 + 0.5 * math.sin(t * (6 + i * 1.7) + i * 1.3)) if animate else 3 + i * 3)
            p.drawRoundedRect(QRectF(x0 + i * (bw + gap), r.center().y() + 7 - h, bw, h), 1.4, 1.4)


class Header(QWidget):
    sortRequested = Signal(str)

    def __init__(self, view):
        super().__init__()
        self.v = view
        self.setFixedHeight(30)
        self.setFont(font(7.4, QFont.Bold, 1.4))

    def paintEvent(self, _):
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(4, 0, -4 - 10, 0)
        cols = col_rects(r.width(), self.v.show_album)
        p.setFont(self.font())
        p.setPen(QColor(255, 255, 255, 100))
        labels = dict((k, l) for k, l, _, _ in COLS)
        labels["added"] = "PLAYED" if self.v.date_mode == "played" else "ADDED"
        for k, (x, w) in cols.items():
            al = Qt.AlignRight if k in ("plays", "dur") else (Qt.AlignCenter if k == "num" else Qt.AlignLeft)
            pad = -12 if k in ("plays",) else (-8 if k == "dur" else 0)
            xx = r.left() + x + (52 if k == "title" and self.v.show_cover else 0)
            p.drawText(QRectF(xx, 0, w + pad - (52 if k == "title" else 0), self.height()), al | Qt.AlignVCenter, labels[k])
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawLine(int(r.left()), self.height() - 1, int(r.right()), self.height() - 1)


class TrackList(QListView):
    activated_track = Signal(int)

    def __init__(self, parent=None, show_album=True, show_cover=True, number_mode="row", date_mode="added"):
        super().__init__(parent)
        self.show_album, self.show_cover = show_album, show_cover
        self.number_mode, self.date_mode = number_mode, date_mode
        self.playlist_id = None
        self.hover_row = -1
        self.m = TrackModel()
        self.setModel(self.m)
        self.setItemDelegate(TrackDelegate(self))
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QListView.NoFrame)
        self.viewport().setAttribute(Qt.WA_Hover)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.doubleClicked.connect(self._play_idx)
        ctx.art.ready.connect(lambda _k: self.viewport().update())
        ctx.player.trackChanged.connect(lambda _t: self.viewport().update())
        if ctx.downloads is not None:
            for sig in (ctx.downloads.progress, ctx.downloads.finished, ctx.downloads.failed):
                sig.connect(lambda *_a: self.viewport().update())
        ctx.player.favoriteChanged.connect(lambda tid, _f: self.m.refresh_row(tid))
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(70)
        if self.playlist_id is None:
            pass

    def _tick(self):
        cur = ctx.player.current
        if not cur or ctx.player.engine.state != "playing" or not self.isVisible():
            return
        for i, r in enumerate(self.m.rows):
            if r["id"] == cur["id"]:
                rect = self.visualRect(self.m.index(i))
                if rect.intersects(self.viewport().rect()):
                    self.viewport().update(rect)
                break

    def set_tracks(self, rows):
        self.m.set_tracks(rows)

    def tracks(self):
        return self.m.rows

    def ids(self):
        return [r["id"] for r in self.m.rows]

    def selected_tracks(self):
        rows = sorted(i.row() for i in self.selectionModel().selectedIndexes())
        return [self.m.rows[r] for r in rows]

    def _play_idx(self, idx):
        self.play_from(idx.row())

    def play_from(self, row):
        ctx.player.play_tracks(self.ids(), row)

    def mouseMoveEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        r = idx.row() if idx.isValid() else -1
        if r != self.hover_row:
            self.hover_row = r
            self.viewport().update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self.hover_row = -1
        self.viewport().update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        if idx.isValid() and e.button() == Qt.LeftButton:
            r = QRectF(self.visualRect(idx)).adjusted(4, 2, -4, -2)
            cols = col_rects(r.width(), self.show_album)
            x = e.position().x() - r.left()
            fx, fw = cols["fav"]
            nx, nw = cols["num"]
            px, pw = cols["plays"]
            row = self.m.rows[idx.row()]
            if px <= x <= px + pw and row.get("source", "local") != "local":
                ctx.downloads.download(row)
                self.viewport().update()
                return
            if fx <= x <= fx + fw:
                ctx.player.toggle_favorite(self.m.rows[idx.row()]["id"])
                return
            if nx <= x <= nx + nw and not e.modifiers():
                self.play_from(idx.row())
                return
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            idx = self.currentIndex()
            if idx.isValid():
                self.play_from(idx.row())
                return
        super().keyPressEvent(e)

    def _menu(self, pos):
        sel = self.selected_tracks()
        if not sel:
            idx = self.indexAt(pos)
            if not idx.isValid():
                return
            sel = [self.m.rows[idx.row()]]
        rows = sorted(i.row() for i in self.selectionModel().selectedIndexes()) or [self.indexAt(pos).row()]

        def remove():
            ctx.lib.remove_from_playlist(self.playlist_id, rows)
            ctx.win.refresh_playlists()
            ctx.win.reload_current()
        on_rem = remove if self.playlist_id is not None else None
        m = track_menu(self, sel, self.playlist_id, on_rem)
        if m:
            m.exec(self.viewport().mapToGlobal(pos))


class TrackListPanel(QWidget):
    """Column header + list."""

    def __init__(self, parent=None, **kw):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.list = TrackList(self, **kw)
        self.header = Header(self.list)
        lay.addWidget(self.header)
        lay.addWidget(self.list, 1)
