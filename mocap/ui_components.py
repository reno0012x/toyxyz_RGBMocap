"""Small presentation widgets; no model or project state."""
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLayout, QToolButton
from .theme import appearance, current_theme, set_theme


class AppearanceSwitch(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('appearanceSwitch')
        self.setAccessibleName('Appearance')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.buttons = {}
        for mode, label in (('light', 'Light'), ('dark', 'Dark')):
            button = QToolButton(self)
            button.setObjectName('appearanceOption')
            button.setText(label)
            button.setCheckable(True)
            button.setAccessibleName(label + ' appearance')
            button.setToolTip('Use ' + label.lower() + ' appearance. Saved on this computer.')
            button.clicked.connect(lambda checked=False, value=mode: set_theme(QApplication.instance(), value))
            layout.addWidget(button)
            self.buttons[mode] = button
        appearance().changed.connect(self.sync)
        self.sync(current_theme())

    def sync(self, mode):
        for key, button in self.buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(key == mode)
            button.blockSignals(blocked)


class FlowLayout(QLayout):
    """Wrap viewport display controls without imposing a wide minimum window."""
    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self.items = []
        self.setSpacing(spacing)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.arrange(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.arrange(rect, False)

    def sizeHint(self):
        visible = [item.sizeHint() for item in self.items if not item.isEmpty()]
        left, top, right, bottom = self.getContentsMargins()
        return QSize(sum(size.width() for size in visible) + max(0, len(visible)-1)*self.spacing() + left + right,
                     max((size.height() for size in visible), default=0) + top + bottom)

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        return size + QSize(left + right, top + bottom)

    def arrange(self, rect, measure):
        left, top, right, bottom = self.getContentsMargins()
        area = rect.adjusted(left, top, -right, -bottom)
        x, y, line_height = area.x(), area.y(), 0
        for item in self.items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            if x > area.x() and x + hint.width() > area.right() + 1:
                x = area.x()
                y += line_height + self.spacing()
                line_height = 0
            if not measure:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.spacing()
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + bottom
