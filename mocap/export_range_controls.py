"""Shared frame selection for both FBX export dialogs."""

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QSpinBox, QWidget


class ExportFrameRange(QWidget):
    def __init__(self, frame_count, current_frame=1, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.mode = QComboBox()
        self.mode.addItem('All frames', 'all')
        self.mode.addItem('Selected frames', 'range')
        form.addRow('Frame range', self.mode)
        self.first = QSpinBox()
        self.last = QSpinBox()
        for spin in (self.first, self.last):
            spin.setRange(1, max(1, frame_count))
        self.first.setValue(max(1, min(current_frame, frame_count)))
        self.last.setValue(frame_count)
        self.first_label = QLabel('Start frame')
        self.last_label = QLabel('End frame')
        form.addRow(self.first_label, self.first)
        form.addRow(self.last_label, self.last)
        self.mode.currentIndexChanged.connect(self.update_range)
        self.first.valueChanged.connect(self.last.setMinimum)
        self.last.setMinimum(self.first.value())
        self.update_range()

    def update_range(self):
        visible = self.mode.currentData() == 'range'
        for widget in (self.first_label, self.first, self.last_label, self.last):
            widget.setVisible(visible)

    def options(self):
        if self.mode.currentData() == 'range':
            return {'frame_start': self.first.value(), 'frame_end': self.last.value()}
        return {}

    def use_timeline_selection(self, slider):
        selection = getattr(slider, 'export_selection', None)
        if selection is not None:
            first, stop = selection
            self.first.setValue(first + 1)
            self.last.setValue(stop)
            self.mode.setCurrentIndex(1)
