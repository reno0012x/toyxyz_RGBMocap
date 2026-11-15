"""Bone picking and transform handles in the character viewport."""
import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen


AXIS_COLORS = ('#ef6b79', '#85ce76', '#69a9ff')


def segment_distance(point, first, last):
    edge = last - first
    weight = np.clip((point - first) @ edge / max(edge @ edge, 1e-12), 0., 1.)
    return np.linalg.norm(point - first - weight * edge)


def point(value):
    return QPointF(float(value[0]), float(value[1]))


class BoneEditorView:
    def __init__(self, view, controller):
        self.view = view
        self.controller = controller
        self.hits = []
        self.handles = []
        self.drag = None

    def paint(self, painter):
        self.hits.clear()
        self.handles.clear()
        editor = self.controller
        if not editor.is_active():
            return
        pose = editor.current_geometry()
        if pose is None:
            return
        starts, start_depth, _ = self.view.project(pose['heads'])
        ends, end_depth, _ = self.view.project(pose['tails'])
        painter.save()
        selected = None
        for index, name in enumerate(pose['names']):
            if min(start_depth[index], end_depth[index]) <= .08:
                continue
            if name == editor.bone:
                selected = index
            elif not editor.xray:
                continue
            a, b = starts[index], ends[index]
            self.hits.append((name, a, b, start_depth[index]))
            painter.setPen(QPen(QColor(102, 182, 240, 150), 1.25))
            painter.drawLine(point(a), point(b))
            painter.drawEllipse(point(a), 2, 2)
        if selected is not None:
            a, b = starts[selected], ends[selected]
            painter.setPen(QPen(QColor('#ffcb69'), 3))
            painter.drawLine(point(a), point(b))
            painter.drawEllipse(point(a), 4, 4)
            painter.drawText(point(a + [8, -10]), editor.bone)
            if editor.tool != 'select' and not editor.source_mode:
                self.paint_handles(painter, pose, selected, a)
        painter.restore()

    def paint_handles(self, painter, pose, index, center):
        editor = self.controller
        world = pose['poses'][index]
        origin = world[:3, 3]
        _, depth, focal = self.view.project(origin)
        units = max(float(depth), .08) / max(float(focal), 1.)
        u, _, v = np.linalg.svd(world[:3, :3])
        placement = pose['transform']
        world_axes = np.eye(3) if placement is None else np.asarray(placement)[:3, :3]
        axes = u @ v if editor.widget.space.currentData() == 'local' else world_axes
        for axis, color in enumerate(AXIS_COLORS):
            painter.setPen(QPen(QColor(color), 2))
            if editor.tool == 'translate':
                end, _, _ = self.view.project(origin + axes[:, axis] * units * 66)
                line = np.array([center, end])
                painter.drawLine(point(center), point(end))
                painter.drawEllipse(point(end), 4, 4)
                painter.drawText(point(end + [5, -3]), 'XYZ'[axis])
            else:
                angle = np.linspace(0., 2 * np.pi, 49)
                radial = (np.cos(angle)[:, None] * axes[:, (axis + 1) % 3] +
                          np.sin(angle)[:, None] * axes[:, (axis + 2) % 3])
                line, _, _ = self.view.project(origin + radial * units * 48)
                for first, last in zip(line[:-1], line[1:]):
                    painter.drawLine(point(first), point(last))
            self.handles.append((axis, line, units))

    def press(self, event):
        editor = self.controller
        if not editor.is_active() or editor.window.busy:
            return False
        cursor = np.array([event.position().x(), event.position().y()])
        candidates = []
        for axis, line, units in self.handles:
            for first, last in zip(line[:-1], line[1:]):
                distance = segment_distance(cursor, first, last)
                if distance < 7 and np.linalg.norm(last - first) > 1.:
                    candidates.append((distance, axis, last - first, units))
        if candidates and editor.bone:
            _, axis, direction, units = min(candidates, key=lambda item: item[0])
            if editor.begin_drag():
                self.drag = (cursor, axis, direction / np.linalg.norm(direction), units)
                return True
        close = [(segment_distance(cursor, a, b), z, name) for name, a, b, z in self.hits]
        close = [hit for hit in close if hit[0] <= 8.]
        if close:
            editor._ui_action('select_bone', {'bone': min(close)[2]})
            return True
        return False

    def move(self, event):
        if self.drag is None:
            return False
        origin, axis, direction, units = self.drag
        cursor = np.array([event.position().x(), event.position().y()])
        pixels = float((cursor - origin) @ direction)
        self.controller.preview_drag(axis, pixels * (units if self.controller.tool == 'translate' else 1.2))
        return True

    def release(self, event):
        if self.drag is None or event.button() != Qt.LeftButton:
            return False
        self.move(event)
        self.drag = None
        self.controller.finish_drag()
        return True
