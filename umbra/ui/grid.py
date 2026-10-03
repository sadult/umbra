"""Cover grids & shelves (albums, artists, genres, playlists, stream results)."""
from PySide6.QtCore import QAbstractListModel, QModelIndex, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyledItemDelegate

from . import icons
from .context import ctx
from .widgets import font


class ItemModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.items = []

    def set_items(self, items):
        self.beginResetModel()
        self.items = list(items)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.items)

    def data(self, idx, role=Qt.DisplayRole):
        if idx.isValid() and role == Qt.UserRole:
            return self.items[idx.row()]
        if idx.isValid() and role == Qt.DisplayRole:
            return self.items[idx.row()].get("title")
        return None


class CardDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.v = view
        self.ft = font(9.6, QFont.DemiBold)
        self.fs = font(8.4)

    def sizeHint(self, opt, idx):
        return QSize(self.v.cell, self.v.cell + 54)

    def paint(self, p: QPainter, opt, idx):
        it = idx.data(Qt.UserRole)
        if not it:
            return
        p.save()
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        th = ctx.theme
        r = QRectF(opt.rect)
        hov = idx.row() == self.v.hover_row
        k = self.v.hover_k if hov else 0.0
        pad = 8
        s = r.width() - 2 * pad
        lift = 3 * k
        cr = QRectF(r.left() + pad, r.top() + pad - lift, s, s)
        round_ = it.get("round", False)
        radius = s / 2 if round_ else 14
        # hover card plate
        if k > 0.01:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, int(14 * k)))
            p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 18, 18)
        # shadow + accent glow
        p.setPen(Qt.NoPen)
        for i in range(10, 0, -2):
            p.setBrush(QColor(0, 0, 0, int(8 + 6 * k)))
            p.drawRoundedRect(cr.adjusted(-i * .3, i * .6, i * .3, i * 1.0), radius, radius)
        if it.get("tile"):
            self._tile(p, cr, it, k)
        else:
            pm = ctx.art.get(it.get("art") or it, int(s), int(radius))
            p.drawPixmap(cr.toRect(), pm)
        # glass rim on cover
        p.setBrush(Qt.NoBrush)
        g = QLinearGradient(cr.topLeft(), cr.bottomRight())
        g.setColorAt(0, QColor(255, 255, 255, 70))
        g.setColorAt(0.5, QColor(255, 255, 255, 10))
        g.setColorAt(1, QColor(255, 255, 255, 24))
        p.setPen(QPen(g, 1))
        p.drawRoundedRect(cr.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        # play orb
        if k > 0.01 and it.get("playable", True):
            d = 42
            c = QPointF(cr.right() - d / 2 - 10, cr.bottom() - d / 2 - 10 + (1 - k) * 8)
            if round_:
                c = QPointF(cr.center().x(), cr.center().y() + (1 - k) * 8)
            p.setOpacity(k)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 90))
            p.drawEllipse(c + QPointF(0, 3), d / 2, d / 2)
            p.setBrush(QColor(250, 250, 252))
            p.drawEllipse(c, d / 2, d / 2)
            icons.draw(p, "play", QRectF(c.x() - 9, c.y() - 9, 18, 18).translated(1.2, 0), QColor(12, 12, 16))
            p.setOpacity(1)
        # text
        ty = cr.bottom() + 10 + lift
        al = Qt.AlignHCenter if round_ else Qt.AlignLeft
        p.setFont(self.ft)
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(QRectF(cr.left(), ty, s, 18), al | Qt.AlignVCenter,
                   QFontMetrics(self.ft).elidedText(it.get("title") or "", Qt.ElideRight, int(s)))
        p.setFont(self.fs)
        p.setPen(QColor(255, 255, 255, 125))
        p.drawText(QRectF(cr.left(), ty + 19, s, 16), al | Qt.AlignVCenter,
                   QFontMetrics(self.fs).elidedText(it.get("subtitle") or "", Qt.ElideRight, int(s)))
        if it.get("badge"):
            bf = font(6.4, QFont.Bold, 0.6)
            bw = QFontMetrics(bf).horizontalAdvance(it["badge"]) + 10
            br = QRectF(cr.left() + 8, cr.top() + 8, bw, 15)
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(br, 5, 5)
            p.setFont(bf)
            p.setPen(QColor(255, 255, 255, 220))
            p.drawText(br, Qt.AlignCenter, it["badge"])
        p.restore()

    def _tile(self, p, cr, it, k):
        """Typographic tile for genres / smart lists."""
        th = ctx.theme
        path = QPainterPath()
        path.addRoundedRect(cr, 14, 14)
        p.save()
        p.setClipPath(path)
        base = it.get("color") or QColor(30, 30, 36)
        g = QLinearGradient(cr.topLeft(), cr.bottomRight())
        g.setColorAt(0, QColor(base).lighter(140))
        g.setColorAt(1, QColor(10, 10, 13))
        p.fillRect(cr, g)
        rg = QRadialGradient(QPointF(cr.right(), cr.top()), cr.width() * 0.9)
        rg.setColorAt(0, th.acc(int(40 + 30 * k)))
        rg.setColorAt(1, th.acc(0))
        p.fillRect(cr, rg)
        if it.get("icon"):
            icons.draw(p, it["icon"], QRectF(cr.right() - cr.width() * 0.42, cr.bottom() - cr.width() * 0.42,
                                               cr.width() * 0.5, cr.width() * 0.5), QColor(255, 255, 255, 28), 1.2)
        p.setPen(QColor(255, 255, 255, 235))
        p.setFont(font(13, QFont.Bold))
        p.drawText(cr.adjusted(14, 12, -14, -12), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, it.get("tile_text") or it.get("title"))
        p.restore()


class CoverGrid(QListView):
    opened = Signal(object)
    playRequested = Signal(object)
    menuRequested = Signal(object, object)

    def __init__(self, parent=None, cell=184, shelf=False):
        super().__init__(parent)
        self.cell = cell
        self.shelf = shelf
        self.hover_row = -1
        self.hover_k = 0.0
        self.m = ItemModel()
        self.setModel(self.m)
        self.setItemDelegate(CardDelegate(self))
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setMouseTracking(True)
        self.setFrameShape(QListView.NoFrame)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(30)
        self.horizontalScrollBar().setSingleStep(40)
        self.setSpacing(2)
        if shelf:
            self.setFlow(QListView.LeftToRight)
            self.setWrapping(False)
            self.setFixedHeight(cell + 54 + 16)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        ctx.art.ready.connect(lambda _k: self.viewport().update())
        self._t = QTimer(self)
        self._t.timeout.connect(self._anim)

    def set_items(self, items):
        self.m.set_items(items)

    def resizeEvent(self, e):
        if not self.shelf:
            # Use a width that doesn't depend on whether the scrollbar is currently shown — otherwise the
            # grid re-flows, the scrollbar toggles, the width changes again… and the page flickers.
            w = self.width() - 2 * self.frameWidth() - self.verticalScrollBar().sizeHint().width() - 6
            n = max(2, int(w // 184))
            gw = max(120, w // n)
            if gw != self.gridSize().width():
                self.cell = gw - 4
                self.setGridSize(QSize(gw, self.cell + 58))
        super().resizeEvent(e)

    def _anim(self):
        target = 1.0 if self.hover_row >= 0 else 0.0
        self.hover_k += (target - self.hover_k) * 0.3
        if abs(target - self.hover_k) < 0.02:
            self.hover_k = target
            self._t.stop()
        self.viewport().update()

    def mouseMoveEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        r = idx.row() if idx.isValid() else -1
        if r != self.hover_row:
            self.hover_row = r
            self.hover_k = 0.0
            self._t.start(16)
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self.hover_row = -1
        self.viewport().update()

    def wheelEvent(self, e):
        if self.shelf:
            sb = self.horizontalScrollBar()
            sb.setValue(sb.value() - e.angleDelta().y())
            return
        super().wheelEvent(e)

    def mouseReleaseEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        if idx.isValid() and e.button() == Qt.LeftButton:
            it = self.m.items[idx.row()]
            r = QRectF(self.visualRect(idx))
            s = r.width() - 16
            cr = QRectF(r.left() + 8, r.top() + 8, s, s)
            pos = e.position()
            if it.get("round"):
                orb = QPointF(cr.center())
            else:
                orb = QPointF(cr.right() - 31, cr.bottom() - 31)
            if it.get("playable", True) and (pos - orb).manhattanLength() < 34:
                self.playRequested.emit(it)
            else:
                self.opened.emit(it)
        super().mouseReleaseEvent(e)

    def _menu(self, pos):
        idx = self.indexAt(pos)
        if idx.isValid():
            self.menuRequested.emit(self.m.items[idx.row()], self.viewport().mapToGlobal(pos))
