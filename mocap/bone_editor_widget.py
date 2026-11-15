"""Bone animation controls and keyframe tracks, independent of project writes."""
from __future__ import annotations

from contextlib import contextmanager
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .i18n import tr
from .theme import color
from .ui_components import FlowLayout


class BoneKeyframeTimeline(QWidget):
    """Take-local frames. Mouse edits emit requests; the controller owns keys."""

    action_requested = Signal(str, object)
    range_selected = Signal(int, int)
    message = Signal(str)
    LABEL_WIDTH = 158
    RULER_HEIGHT = 26
    ROW_HEIGHT = 27
    RIGHT = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame = self.frames = 1
        self.bone = None
        self.tracks = {}
        self.rows = []
        self.selection = None
        self.enabled = False
        self._seek_drag = False
        self._key_drag = None
        self._range_drag = None
        self._selected_key = None
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumHeight(112)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setToolTip(tr('Left drag: seek or move a key. Middle drag: select frames. Double-click: add a key.'))

    def set_state(self, frame=None, frames=None, bone=None, layer=None, selection=None, ready=None):
        if frames is not None:
            self.frames = max(1, int(frames))
        if frame is not None:
            self.frame = max(1, min(self.frames, int(frame)))
        self.bone = bone
        if layer is not None:
            self.tracks = layer.get('tracks', {})
        if ready is not None:
            self.enabled = bool(ready)
        self.selection = tuple(selection) if selection is not None else None
        self.rows = ([self.bone] if self.bone else []) + [
            name for name, track in self.tracks.items()
            if name != self.bone and track.get('keys')
        ]
        self.setMinimumHeight(max(112, self.RULER_HEIGHT + len(self.rows) * self.ROW_HEIGHT + 8))
        if self._selected_key and self._selected_key[0] not in self.rows:
            self._selected_key = None
        self.update()

    def frame_x(self, frame):
        span = max(1, self.frames - 1)
        return self.LABEL_WIDTH + (frame - 1) / span * max(1, self.width() - self.LABEL_WIDTH - self.RIGHT)

    def frame_at(self, x):
        fraction = (x - self.LABEL_WIDTH) / max(1, self.width() - self.LABEL_WIDTH - self.RIGHT)
        return max(1, min(self.frames, round(1 + fraction * max(1, self.frames - 1))))

    def _row(self, y):
        index = int((y - self.RULER_HEIGHT) // self.ROW_HEIGHT)
        return self.rows[index] if y >= self.RULER_HEIGHT and 0 <= index < len(self.rows) else None

    def _keys(self, bone):
        return [int(key['frame']) + 1 for key in self.tracks.get(bone, {}).get('keys', [])]

    def _key_at(self, point):
        bone = self._row(point.y())
        if bone is None:
            return None
        matches = [(abs(self.frame_x(frame) - point.x()), frame) for frame in self._keys(bone)]
        distance, frame = min(matches, default=(float('inf'), None))
        return (bone, frame) if distance <= 8 else None

    def _request(self, action, **args):
        self.action_requested.emit(action, args)

    def mousePressEvent(self, event):
        if not self.enabled:
            return
        self.setFocus(Qt.MouseFocusReason)
        point = event.position()
        if event.button() == Qt.MiddleButton and point.x() >= self.LABEL_WIDTH:
            frame = self.frame_at(point.x())
            self._range_drag = frame
            self.selection = (frame, frame)
            self.range_selected.emit(frame, frame)
            self.update()
        elif event.button() == Qt.LeftButton:
            bone = self._row(point.y())
            if bone:
                self._request('select_bone', bone=bone)
            if point.x() >= self.LABEL_WIDTH:
                hit = self._key_at(point)
                self._selected_key = hit
                if hit:
                    self._key_drag = (hit[0], hit[1], hit[1], point.x())
                    self._request('seek', frame=hit[1])
                else:
                    self._seek_drag = True
                    self._request('seek', frame=self.frame_at(point.x()))
                self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        frame = self.frame_at(event.position().x())
        if self._range_drag is not None:
            self.selection = (min(frame, self._range_drag), max(frame, self._range_drag))
            self.range_selected.emit(*self.selection)
            self.update()
        elif self._key_drag is not None:
            bone, original, _, pixel = self._key_drag
            self._key_drag = (bone, original, frame, pixel)
            self.update()
        elif self._seek_drag:
            self._request('seek', frame=frame)
        else:
            self.setCursor(Qt.SizeHorCursor if self.enabled and self._key_at(event.position()) else Qt.ArrowCursor)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._range_drag is not None:
            frame = self.frame_at(event.position().x())
            self.selection = (min(frame, self._range_drag), max(frame, self._range_drag))
            self._range_drag = None
            self.range_selected.emit(*self.selection)
        elif event.button() == Qt.LeftButton:
            if self._key_drag is not None:
                bone, first, last, pixel = self._key_drag
                last = self.frame_at(event.position().x())
                if last != first and abs(event.position().x() - pixel) >= 3:
                    if last in self._keys(bone):
                        self.message.emit(tr('A keyframe already exists at the destination frame.'))
                    else:
                        self._request('move_keyframe', bone=bone, frame=first, new_frame=last)
                        self._selected_key = (bone, last)
                self._key_drag = None
            self._seek_drag = False
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if self.enabled and event.button() == Qt.LeftButton and event.position().x() >= self.LABEL_WIDTH:
            bone = self._row(event.position().y()) or self.bone
            if bone:
                frame = self.frame_at(event.position().x())
                self._request('select_bone', bone=bone)
                self._request('seek', frame=frame)
                self._request('add_key', bone=bone, frame=frame)
            event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self._selected_key and self.enabled:
            self._request('delete_keyframe', bone=self._selected_key[0], frame=self._selected_key[1])
            event.accept()
        elif event.key() == Qt.Key_Escape:
            self.selection = None
            self._key_drag = self._range_drag = None
            self.range_selected.emit(0, 0)
            self.update()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(color('canvas')))
        painter.fillRect(QRectF(0, 0, self.LABEL_WIDTH, self.height()), QColor(color('surface')))
        if self.selection:
            left, right = (self.frame_x(x) for x in self.selection)
            tint = QColor(color('accent'))
            tint.setAlpha(45)
            painter.fillRect(QRectF(left, 0, max(2, right - left), self.height()), tint)
        width = max(1, self.width() - self.LABEL_WIDTH - self.RIGHT)
        desired = max(1, (self.frames - 1) / max(1, width / 75))
        power = 10 ** math.floor(math.log10(desired))
        step = next((multiple * power for multiple in (1, 2, 5, 10) if multiple * power >= desired), power * 10)
        step = max(1, int(step))
        painter.setPen(QColor(color('canvas_muted')))
        painter.drawText(QRectF(8, 0, self.LABEL_WIDTH - 16, self.RULER_HEIGHT), Qt.AlignVCenter, tr('Bone tracks'))
        for frame in range(1, self.frames + 1, step):
            x = self.frame_x(frame)
            painter.setPen(QColor(color('grid_minor')))
            painter.drawLine(QPointF(x, self.RULER_HEIGHT), QPointF(x, self.height()))
            painter.setPen(QColor(color('canvas_muted')))
            painter.drawText(QRectF(x + 3, 1, 60, 21), Qt.AlignVCenter, str(frame))
        for row, bone in enumerate(self.rows):
            y = self.RULER_HEIGHT + row * self.ROW_HEIGHT
            if bone == self.bone:
                painter.fillRect(QRectF(0, y, self.width(), self.ROW_HEIGHT), QColor(color('selection')))
            painter.setPen(QColor(color('divider')))
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
            painter.setPen(QColor(color('text')))
            label = painter.fontMetrics().elidedText(bone, Qt.ElideMiddle, self.LABEL_WIDTH - 16)
            painter.drawText(QRectF(8, y, self.LABEL_WIDTH - 16, self.ROW_HEIGHT), Qt.AlignVCenter, label)
            center_y = y + self.ROW_HEIGHT / 2
            for frame in self._keys(bone):
                x = self.frame_x(frame)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(color('warning') if self._selected_key == (bone, frame) else color('accent')))
                painter.drawPolygon(QPolygonF([QPointF(x, center_y - 5), QPointF(x + 5, center_y),
                                               QPointF(x, center_y + 5), QPointF(x - 5, center_y)]))
        if self._key_drag:
            bone, _, frame, _ = self._key_drag
            if bone in self.rows:
                x = self.frame_x(frame)
                y = self.RULER_HEIGHT + self.rows.index(bone) * self.ROW_HEIGHT + self.ROW_HEIGHT / 2
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(color('warning')), 2))
                painter.drawEllipse(QPointF(x, y), 6, 6)
        x = self.frame_x(self.frame)
        painter.setPen(QPen(QColor(color('accent')), 1.5))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        if not self.rows:
            painter.setPen(QColor(color('muted')))
            painter.drawText(QRectF(self.LABEL_WIDTH + 12, 40, width - 20, 50), Qt.TextWordWrap,
                             tr('Select a bone to edit its keyframes.'))


class BoneEditorWidget(QWidget):
    action_requested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._muting = 0
        self._busy = False
        self._ready = False
        self._source_mode = False
        self._characters = []
        self._bone_items = {}
        self._selected_bone = None
        self._layer = {'enabled': True, 'tracks': {}}
        self._state = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(5)
        target_bar = QWidget()
        top = FlowLayout(target_bar, spacing=6)
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(QLabel(tr('Motion target')))
        self.character = QComboBox()
        self.character.setFixedWidth(208)
        self.character.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.character.setMinimumContentsLength(14)
        self.character.setProperty('i18nSkipItems', True)
        self.character.setToolTip(tr('Choose a source person or retargeted character.'))
        top.addWidget(self.character)
        self.take = QComboBox()
        self.take.setFixedWidth(160)
        self.take.setProperty('i18nSkipItems', True)
        top.addWidget(self.take)
        self.prepare_button = self._button('Prepare Bone Editor', lambda: self._emit('prepare'))
        top.addWidget(self.prepare_button)
        self.layer_enabled = QCheckBox(tr('Enable edit layer'))
        self.layer_enabled.setChecked(True)
        self.layer_enabled.toggled.connect(lambda checked: self._emit('set_enabled', enabled=checked))
        top.addWidget(self.layer_enabled)
        self.undo_button = self._button('Undo', lambda: self._emit('undo'))
        self.redo_button = self._button('Redo', lambda: self._emit('redo'))
        self.save_button = self._button('Save edits', lambda: self._emit('save'))
        for button in (self.undo_button, self.redo_button, self.save_button):
            top.addWidget(button)
        self.source_badge = QLabel(tr('Source motion · view only'))
        self.source_badge.setObjectName('muted')
        top.addWidget(self.source_badge)
        root.addWidget(target_bar)
        splitter = QSplitter(Qt.Horizontal)
        tree_panel = QWidget()
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(3)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Search bones'))
        from .i18n import localizer
        localizer().changed.connect(lambda *_: self.search.setPlaceholderText(tr('Search bones')))
        self.search.textChanged.connect(self._filter_bones)
        tree_layout.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.currentItemChanged.connect(self._bone_selected)
        tree_layout.addWidget(self.tree)
        splitter.addWidget(tree_panel)
        edit_panel = QWidget()
        edit_layout = QVBoxLayout(edit_panel)
        edit_layout.setContentsMargins(5, 0, 0, 0)
        edit_layout.setSpacing(4)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(5)
        self.bone_label = QLabel(tr('No bone selected'))
        self.bone_label.setMinimumWidth(108)
        self.bone_label.setMaximumWidth(180)
        self.bone_label.setProperty('i18nDataText', True)
        toolbar.addWidget(self.bone_label)
        self.tool_buttons = {}
        self.tool_group = QButtonGroup(self)
        for key, label in (('select', 'Select'), ('translate', 'Move'), ('rotate', 'Rotate')):
            button = self._button(label, lambda checked=False, tool=key: self._emit('set_tool', tool=tool))
            button.setCheckable(True)
            self.tool_group.addButton(button)
            self.tool_buttons[key] = button
            toolbar.addWidget(button)
        self.tool_buttons['rotate'].setChecked(True)
        self.xray = QCheckBox(tr('X-Ray'))
        self.xray.setChecked(True)
        self.xray.toggled.connect(lambda checked: self._emit('set_xray', enabled=checked))
        toolbar.addWidget(self.xray)
        self.frame_number = QSpinBox()
        self.frame_number.setRange(1, 1)
        self.frame_number.setPrefix(tr('Frame') + ' ')
        self.frame_number.setFixedWidth(122)
        self.frame_number.valueChanged.connect(lambda value: self._emit('seek', frame=value))
        toolbar.addWidget(self.frame_number)
        toolbar.addStretch(1)
        localizer().changed.connect(self._language_changed)
        edit_layout.addLayout(toolbar)
        self.offset_panel = QWidget()
        controls = QGridLayout(self.offset_panel)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(6)
        controls.setVerticalSpacing(3)
        controls.setAlignment(Qt.AlignLeft)
        self.space = QComboBox()
        self.space.addItem(tr('Local'), 'local')
        self.space.addItem(tr('World'), 'world')
        self.space.setMinimumWidth(114)
        self.space.setMaximumWidth(165)
        controls.addWidget(self.space, 0, 0)
        self.translation = []
        self.rotation = []
        for column, axis in enumerate('XYZ', 1):
            axis_label = QLabel(axis)
            axis_label.setAlignment(Qt.AlignCenter)
            controls.addWidget(axis_label, 0, column)
        controls.addWidget(QLabel(tr('Position offset (m)')), 1, 0)
        controls.addWidget(QLabel(tr('Rotation offset (°)')), 2, 0)
        for row, values, limit, decimals, step in ((1, self.translation, 1000., 4, .01), (2, self.rotation, 36000., 2, 1.)):
            for column in range(1, 4):
                spin = QDoubleSpinBox()
                spin.setRange(-limit, limit)
                spin.setDecimals(decimals)
                spin.setSingleStep(step)
                spin.setFixedWidth(86)
                spin.setKeyboardTracking(False)
                spin.editingFinished.connect(self._auto_key)
                controls.addWidget(spin, row, column)
                values.append(spin)
        self.auto_key = QCheckBox(tr('Auto Key'))
        self.auto_key.setChecked(True)
        controls.addWidget(self.auto_key, 1, 4)
        self.reset_button = self._button('Reset offset', self._reset_offset)
        controls.addWidget(self.reset_button, 2, 4)
        edit_layout.addWidget(self.offset_panel)
        self.key_controls = QWidget()
        keys = FlowLayout(self.key_controls, spacing=5)
        keys.setContentsMargins(0, 0, 0, 0)
        self.add_key_button = self._button('Add / Update Key', self._add_key)
        self.delete_key_button = self._button('Delete Key', lambda: self._emit('delete_keyframe', bone=self.selected_bone, frame=self.frame_number.value()))
        self.clear_track_button = self._button('Clear bone track', lambda: self._emit('clear_track', bone=self.selected_bone))
        keys.addWidget(self.add_key_button)
        keys.addWidget(self.delete_key_button)
        self.range_start = QSpinBox()
        self.range_end = QSpinBox()
        for spin in (self.range_start, self.range_end):
            spin.setRange(1, 1)
            spin.setFixedWidth(68)
        self.range_start.setToolTip(tr('Start frame'))
        self.range_end.setToolTip(tr('End frame'))
        keys.addWidget(self.range_start)
        keys.addWidget(QLabel('–'))
        keys.addWidget(self.range_end)
        self.range_button = self._button('Apply to range', self._apply_range)
        keys.addWidget(self.range_button)
        keys.addWidget(self.clear_track_button)
        edit_layout.addWidget(self.key_controls)
        self.timeline = BoneKeyframeTimeline()
        self.timeline.action_requested.connect(self._timeline_action)
        self.timeline.range_selected.connect(self._range_selected)
        self.timeline.message.connect(self._message)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(self.timeline)
        scroll.setMinimumHeight(95)
        edit_layout.addWidget(scroll, 1)
        splitter.addWidget(edit_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 800])
        root.addWidget(splitter, 1)
        self.status = QLabel(tr('Select a retargeted character, then prepare its bones.'))
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.character.currentIndexChanged.connect(self._character_selected)
        self.take.currentIndexChanged.connect(self._take_selected)
        self._shortcuts = []
        for shortcut, callback in (('Ctrl+Z', lambda: self.undo_button.click()),
                                   ('Ctrl+Y', lambda: self.redo_button.click()),
                                   ('Ctrl+Shift+Z', lambda: self.redo_button.click()),
                                   ('W', lambda: self.tool_buttons['translate'].click()),
                                   ('E', lambda: self.tool_buttons['rotate'].click()),
                                   ('Q', lambda: self.tool_buttons['select'].click())):
            key = QShortcut(QKeySequence(shortcut), self)
            key.setContext(Qt.WidgetWithChildrenShortcut)
            key.activated.connect(callback)
            self._shortcuts.append(key)
        self.setMinimumHeight(260)
        self._sync_enabled()

    @property
    def selected_bone(self):
        return self._selected_bone

    @contextmanager
    def _quiet(self):
        self._muting += 1
        try:
            yield
        finally:
            self._muting -= 1

    def _button(self, text, callback):
        button = QPushButton(tr(text))
        button.clicked.connect(callback)
        return button

    def _emit(self, action, **args):
        if self._source_mode and action not in {'select_character', 'select_bone', 'seek', 'set_xray', 'set_tool'}:
            return
        if self._source_mode and action == 'set_tool' and args.get('tool') != 'select':
            return
        if not self._muting and not self._busy:
            self.action_requested.emit(action, args)

    def _message(self, text):
        self.status.setText(text)

    def _language_changed(self, *_):
        with self._quiet():
            self.frame_number.setPrefix(tr('Frame') + ' ')
            self._populate_takes(max(0, self.take.currentIndex()))
            self._update_bone_label()
        self.timeline.update()

    def _update_bone_label(self):
        text = self._selected_bone or tr('No bone selected')
        self.bone_label.setText(self.bone_label.fontMetrics().elidedText(text, Qt.ElideMiddle, 180))
        self.bone_label.setToolTip(text if self._selected_bone else '')

    def _transform(self):
        return dict(bone=self.selected_bone, frame=self.frame_number.value(),
                    translation=[spin.value() for spin in self.translation],
                    rotation=[spin.value() for spin in self.rotation], space=self.space.currentData())

    def _add_key(self):
        if self.selected_bone and self._ready:
            self._emit('set_keyframe', **self._transform())

    def _auto_key(self):
        if self.auto_key.isChecked() and not self._muting:
            self._add_key()

    def _reset_offset(self):
        with self._quiet():
            for spin in self.translation + self.rotation:
                spin.setValue(0.)
        self._add_key()

    def _apply_range(self):
        if not self.selected_bone or not self._ready:
            return
        args = self._transform()
        args.pop('frame')
        first, last = sorted((self.range_start.value(), self.range_end.value()))
        self._emit('set_range', frame_start=first, frame_end=last, **args)

    def _timeline_action(self, action, args):
        if action == 'add_key':
            values = self._transform()
            values.update(args)
            self._emit('set_keyframe', **values)
        else:
            self._emit(action, **args)

    def _range_selected(self, first, last):
        if first <= 0 or last <= 0:
            self._state['selection'] = None
            return
        self._state['selection'] = (first, last)
        self.range_start.setValue(first)
        self.range_end.setValue(last)

    def _character_selected(self, index):
        if self._muting:
            return
        with self._quiet():
            self._populate_takes(0)
        self._ready = False
        self._sync_enabled()
        self._emit('select_character', character_id=self.character.currentData(), take_index=0)

    def _take_selected(self, index):
        if not self._muting:
            self._ready = False
            self._sync_enabled()
            self._emit('select_character', character_id=self.character.currentData(), take_index=max(0, index))

    def _populate_takes(self, index):
        self.take.clear()
        character = next((c for c in self._characters if c.get('id') == self.character.currentData()), None)
        for number, take in enumerate(character.get('takes', []) if character else []):
            self.take.addItem(f"{tr('Take')} {number + 1} · {take.get('frames', 0)} {tr('frames')}", number)
        if self.take.count():
            self.take.setCurrentIndex(max(0, min(index, self.take.count() - 1)))

    def set_characters(self, characters):
        self._characters = list(characters)
        previous, take = self.character.currentData(), self.take.currentIndex()
        with self._quiet():
            self.character.clear()
            for character in self._characters:
                self.character.addItem(character['name'], character['id'])
            found = self.character.findData(previous)
            if found >= 0:
                self.character.setCurrentIndex(found)
            self._populate_takes(max(0, take))
        self._sync_enabled()

    def _bone_selected(self, current, previous):
        self._selected_bone = current.data(0, Qt.UserRole) if current else None
        self._update_bone_label()
        self._sync_enabled()
        self._refresh_timeline()
        if self._selected_bone:
            self._emit('select_bone', bone=self._selected_bone)

    def set_skeleton(self, names, parents):
        if len(names) != len(parents) or len(set(names)) != len(names):
            raise ValueError('Invalid bone hierarchy')
        # Validate before constructing Qt parent links, including cycles.
        for index in range(len(names)):
            seen, cursor = set(), index
            while cursor >= 0:
                if cursor >= len(names) or cursor in seen:
                    raise ValueError('Invalid bone hierarchy')
                seen.add(cursor)
                cursor = int(parents[cursor])
        previous = self.selected_bone
        with self._quiet():
            self.tree.clear()
            self._bone_items = {name: QTreeWidgetItem([name]) for name in names}
            for index, name in enumerate(names):
                item = self._bone_items[name]
                item.setData(0, Qt.UserRole, name)
                item.setToolTip(0, name)
                parent = int(parents[index])
                if parent >= 0:
                    self._bone_items[names[parent]].addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
            self.tree.expandToDepth(1)
            self._selected_bone = previous if previous in self._bone_items else None
            if self._selected_bone:
                self.tree.setCurrentItem(self._bone_items[self._selected_bone])
            self._update_bone_label()
            self._filter_bones(self.search.text())
        self._sync_enabled()
        self._refresh_timeline()

    def _filter_bones(self, text):
        query = text.casefold().strip()
        def visible(item):
            child_match = False
            for index in range(item.childCount()):
                child_match = visible(item.child(index)) or child_match
            matches = not query or query in item.text(0).casefold() or child_match
            item.setHidden(not matches)
            if query and child_match:
                item.setExpanded(True)
            return matches
        for index in range(self.tree.topLevelItemCount()):
            visible(self.tree.topLevelItem(index))

    def set_frame(self, frame, total):
        with self._quiet():
            total = max(1, int(total))
            self.frame_number.setMaximum(total)
            self.frame_number.setValue(max(1, min(total, int(frame))))
            self.range_start.setMaximum(total)
            self.range_end.setMaximum(total)
        self._refresh_timeline()

    def set_layer(self, layer):
        self._layer = layer or {'enabled': True, 'tracks': {}}
        with self._quiet():
            self.layer_enabled.setChecked(bool(self._layer.get('enabled', True)))
        self._refresh_timeline()

    def set_state(self, state):
        self._state.update(state)
        with self._quiet():
            if 'character_id' in state:
                index = self.character.findData(state['character_id'])
                if index >= 0 and index != self.character.currentIndex():
                    self.character.setCurrentIndex(index)
                    self._populate_takes(state.get('take_index', 0))
            if 'take_index' in state and 0 <= state['take_index'] < self.take.count():
                self.take.setCurrentIndex(state['take_index'])
            if 'bone' in state:
                self._selected_bone = state['bone'] if state['bone'] in self._bone_items else None
                self.tree.setCurrentItem(self._bone_items.get(self._selected_bone))
                if self._selected_bone:
                    self.tree.scrollToItem(self._bone_items[self._selected_bone])
                self._update_bone_label()
            self.set_frame(state.get('frame', self.frame_number.value()), state.get('frames', self.frame_number.maximum()))
            for key, spins in (('translation', self.translation), ('rotation', self.rotation)):
                if key in state:
                    for spin, value in zip(spins, state[key]):
                        if math.isfinite(float(value)):
                            spin.setValue(float(value))
            if 'space' in state:
                index = self.space.findData(state['space'])
                if index >= 0:
                    self.space.setCurrentIndex(index)
            if 'enabled' in state:
                self.layer_enabled.setChecked(bool(state['enabled']))
            if 'xray' in state:
                self.xray.setChecked(bool(state['xray']))
            if state.get('tool') in self.tool_buttons:
                self.tool_buttons[state['tool']].setChecked(True)
            if 'status' in state:
                self.status.setText(state['status'])
            if 'ready' in state:
                self._ready = bool(state['ready'])
            if 'source_mode' in state:
                self._source_mode = bool(state['source_mode'])
            if 'selection' in state:
                selection = state['selection']
                if selection is not None:
                    self.range_start.setValue(selection[0])
                    self.range_end.setValue(selection[1])
        self._sync_enabled()
        self._refresh_timeline()

    def set_busy(self, busy, message=''):
        self._busy = bool(busy)
        if message:
            self.status.setText(message)
        self._sync_enabled()

    def _sync_enabled(self):
        has_character = self.character.currentIndex() >= 0
        ready = self._ready and not self._busy
        eligible = self._ready and not self._source_mode
        edit_ready = ready and eligible
        selected = edit_ready and self.selected_bone is not None
        self.character.setEnabled(not self._busy)
        self.take.setEnabled(not self._busy and self.take.count() > 0)
        self.prepare_button.setVisible(has_character and not self._source_mode and not self._ready)
        self.prepare_button.setEnabled(not self._busy and has_character and self.take.count() > 0)
        self.tree.setEnabled(ready)
        self.search.setEnabled(ready)
        self.offset_panel.setVisible(eligible)
        self.key_controls.setVisible(eligible)
        self.source_badge.setVisible(self._source_mode)
        for control in (self.layer_enabled, self.save_button, self.undo_button, self.redo_button):
            control.setVisible(eligible)
        self.layer_enabled.setEnabled(edit_ready)
        self.save_button.setEnabled(edit_ready)
        self.undo_button.setEnabled(edit_ready and bool(self._state.get('can_undo')))
        self.redo_button.setEnabled(edit_ready and bool(self._state.get('can_redo')))
        has_track = selected and bool(self._layer.get('tracks', {}).get(self.selected_bone))
        self.clear_track_button.setEnabled(has_track)
        for control in self.translation + self.rotation + [self.reset_button, self.add_key_button,
                self.delete_key_button, self.range_button, self.auto_key]:
            control.setEnabled(selected)
        self.space.setEnabled(selected and not has_track)
        for control in (self.frame_number, self.xray, self.tool_buttons['select']):
            control.setEnabled(ready)
        for control in (self.range_start, self.range_end):
            control.setEnabled(edit_ready)
        for tool in ('translate', 'rotate'):
            self.tool_buttons[tool].setVisible(eligible)
            self.tool_buttons[tool].setEnabled(edit_ready)
        if self._source_mode:
            self.tool_buttons['select'].setChecked(True)
        self.timeline.enabled = ready

    def _refresh_timeline(self):
        layer = {'tracks': {}} if self._source_mode else self._layer
        self.timeline.set_state(frame=self.frame_number.value(), frames=self.frame_number.maximum(),
                                bone=self.selected_bone, layer=layer,
                                selection=self._state.get('selection'), ready=self._ready and not self._busy)
