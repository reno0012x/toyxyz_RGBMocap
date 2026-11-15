"""Floating presentation for the same Bone Editor widget and controller."""

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QSizePolicy, QTabBar, QVBoxLayout, QWidget


class TimelineTabBar(QTabBar):
    detach_requested = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setExpanding(False)
        self.setUsesScrollButtons(False)
        self.setElideMode(Qt.ElideNone)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._drag_origin = None

    def mousePressEvent(self, event):
        point = event.position().toPoint()
        self._drag_origin = point if event.button() == Qt.LeftButton and self.tabAt(point) == 1 else None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        point = event.position().toPoint()
        outside = not self.rect().adjusted(-8, -8, 8, 8).contains(point)
        detach = (event.button() == Qt.LeftButton and self._drag_origin is not None and outside and
                  (point - self._drag_origin).manhattanLength() >= QApplication.startDragDistance())
        self._drag_origin = None
        super().mouseReleaseEvent(event)
        if detach:
            self.detach_requested.emit(event.globalPosition().toPoint())


class BoneEditorWindow(QWidget):
    dock_requested = Signal()

    def __init__(self, owner):
        super().__init__(owner, Qt.Window)
        self.setWindowTitle('Bone Editor')
        self.setObjectName('editor')
        self.setMinimumSize(690, 345)
        self.resize(990, 420)
        self._hidden_with_owner = False
        owner.installEventFilter(self)
        self.editor_layout = QVBoxLayout(self)
        self.editor_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_layout.setSpacing(0)
        header = QHBoxLayout()
        header.setContentsMargins(8, 6, 8, 0)
        header.addStretch(1)
        self.dock_button = QPushButton('Dock Bone Editor')
        self.dock_button.clicked.connect(self.dock_requested.emit)
        header.addWidget(self.dock_button)
        self.editor_layout.addLayout(header)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget():
            if event.type() == QEvent.Hide and self.isVisible():
                self._hidden_with_owner = True
                self.hide()
            elif event.type() == QEvent.Show and self._hidden_with_owner:
                self._hidden_with_owner = False
                self.show()
        return super().eventFilter(watched, event)

    def place_near(self, position):
        screen = QApplication.screenAt(position) or self.parentWidget().screen()
        if screen is not None:
            area = screen.availableGeometry()
            x = max(area.left(), min(position.x() - 120, area.right() - self.width()))
            y = max(area.top(), min(position.y() - 25, area.bottom() - self.height()))
            self.move(x, y)

    def closeEvent(self, event):
        self._hidden_with_owner = False
        self.dock_requested.emit()
        event.accept()
