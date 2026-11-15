"""Private stdio session for inspecting and exporting saved motion."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Event, Thread
import time

from PySide6.QtCore import QByteArray, QBuffer, QEvent, QEventLoop, QIODevice, QObject, QTimer, Qt, Signal

from .capture import capture_window
from .gui import MainWindow
from .motion_tools import base_result, result_is_current
from .paths import HOME, ROOT
from .preview_data import project_signature
from .result_artifacts import artifacts_current


REQUEST_LIMIT = 64 * 1024
WAIT_SECONDS = 18
BONE_ACTIONS = {
    'bone_editor_status': 'status', 'list_bones': 'list_bones',
    'select_bone': 'select_bone', 'get_bone_pose': 'get_pose',
    'set_bone_keyframe': 'set_keyframe', 'delete_bone_keyframe': 'delete_keyframe',
    'move_bone_keyframe': 'move_keyframe', 'set_bone_range': 'set_range',
    'set_bone_layer_enabled': 'set_enabled', 'bone_editor_history': 'history',
    'clear_bone_track': 'clear_track', 'save_bone_edits': 'save',
    'select_motion_target': 'select_character', 'analyze_motion_range': 'analyze_motion',
    'remember_motion_example': 'remember_motion', 'search_motion_examples': 'search_memory',
    'forget_motion_example': 'forget_motion',
}


class Inspection(QObject):
    request = Signal(object)
    disconnected = Signal()

    def __init__(self, app, window, output):
        super().__init__(window)
        self.app = app
        self.window = window
        self.output = output
        self.loaded = False
        self.closed = False
        self.video_error = None
        self.preview_error = None
        self.scene_error = None
        self.deadline = 0.0
        self.handled = Event()
        self.request.connect(self.dispatch)
        self.disconnected.connect(self.disconnect)
        window.video_view.decode_error.connect(self.on_video_error)
        window.data_loader.failed.connect(self.on_preview_error)
        window.scene_loader.failed.connect(self.on_scene_error)
        window.setAcceptDrops(False)
        app.installEventFilter(self)

    def eventFilter(self, obj, event):
        # This window belongs to the MCP connection. Keep interactive shortcuts
        # and pointer actions from editing the projects it inspects.
        return event.type() in {
            QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick,
            QEvent.KeyPress, QEvent.KeyRelease, QEvent.Shortcut, QEvent.Wheel,
            QEvent.ContextMenu, QEvent.DragEnter, QEvent.Drop,
        }

    def on_video_error(self, message):
        self.video_error = message

    def on_preview_error(self, generation, message):
        if generation == self.window.data_loader.generation:
            self.preview_error = message

    def on_scene_error(self, generation, message):
        if generation == self.window.scene_loader.generation:
            self.scene_error = message

    def read_requests(self, stream):
        while True:
            line = stream.readline(REQUEST_LIMIT + 1)
            if not line or len(line) > REQUEST_LIMIT:
                self.disconnected.emit()
                return
            try:
                message = json.loads(line)
            except (ValueError, UnicodeError):
                self.disconnected.emit()
                return
            self.handled.clear()
            self.request.emit(message)
            self.handled.wait()

    def disconnect(self):
        self.closed = True
        self.app.quit()

    def dispatch(self, request):
        if not isinstance(request, dict):
            self.handled.set()
            self.disconnect()
            return
        reply = {'id': request.get('id')}
        self.deadline = time.monotonic() + (195 if request.get('action') in BONE_ACTIONS else 60)
        try:
            actions = {'status': self.status, 'open_project': self.open_project,
                       'seek_frame': self.seek_frame, 'capture_view': self.capture_view,
                       'compare_motion': self.compare_motion, 'export_fbx': self.export_fbx,
                       'select_frame_range': self.select_frame_range}
            if request['action'] in BONE_ACTIONS:
                reply['result'] = self.bone_tool(request['action'], **request['arguments'])
            else:
                reply['result'] = actions[request['action']](**request['arguments'])
        except Exception as error:
            reply['error'] = str(error) or type(error).__name__
        try:
            self.output.write(json.dumps(reply, ensure_ascii=False).encode('utf-8') + b'\n')
            self.output.flush()
        except OSError:
            self.disconnect()
        finally:
            self.handled.set()

    def wait_for(self, predicate, description, error=None):
        deadline = min(self.deadline, time.monotonic() + WAIT_SECONDS)
        while not predicate():
            problem = error() if error else None
            if problem:
                raise RuntimeError(f'{description}: {problem}')
            if self.closed or not self.window.isVisible():
                raise RuntimeError('The inspection window closed.')
            if time.monotonic() >= deadline:
                raise TimeoutError(f'Timed out waiting for {description}.')
            loop = QEventLoop()
            QTimer.singleShot(20, loop.quit)
            loop.exec()

    def status(self):
        w = self.window
        loaded = self.loaded
        controller = getattr(w, 'bone_editor_controller', None)
        bone_editor = controller.dispatch('status') if loaded and controller is not None else None
        return {
            'workspace': str(w.workspace_root) if loaded and w.workspace_root else None,
            'project': str(w.project) if loaded and w.project else None,
            'model': w.model_choice.currentData() if loaded else None,
            'person_id': w.active_person_id if loaded else None,
            'frames': int(w.info['frames']) if loaded and w.info else 0,
            'frame': int(w.slider.value()) + 1 if loaded and w.info else None,
            'presented_frame': int(w.video_view.index) + 1 if loaded and w.video_view.frame is not None else None,
            'result': w.active_result if loaded and w.project else None,
            'motion_ready': bool(loaded and w.slider.has_motion),
            'selected_frames': ([w.slider.export_selection[0]+1, w.slider.export_selection[1]]
                                if loaded and w.slider.export_selection is not None else None),
            'characters': [{'id': c['id'], 'name': c['name'],
                            'motion_ready': bool(c.get('takes')) and not c.get('needs_retarget', False),
                            'takes': [{'take_index': index, 'frames': take['frames'],
                                       'fps': take['fps'], 'start': take['start']}
                                      for index, take in enumerate(c.get('takes', []))]}
                           for c in w.characters] if loaded else [],
            'bone_editor': bone_editor,
            'status': w.status.text(),
        }

    def bone_tool(self, tool_name, **arguments):
        """Explicit opt-in editing boundary for the otherwise read-only session.

        The controller owns character/take identities, paths, preparation and
        atomic layer saves. No generic Python, inference or project write API is
        exposed through this bridge.
        """
        w = self.window
        if not self.loaded or w.project is None:
            raise ValueError('Open a saved project with a retargeted character first.')
        if getattr(w, 'busy', False) or getattr(w, 'contact_saving', False):
            raise RuntimeError('Wait for the current processing or contact save to finish.')
        controller = getattr(w, 'bone_editor_controller', None)
        if controller is None:
            raise RuntimeError('The Bone Editor is unavailable. Restart RGB MoCap with the current source.')
        action = BONE_ACTIONS[tool_name]
        if action == 'history':
            action = arguments.pop('action')
        if action != 'status':
            w.stop_playback()
        if action in ('select_bone', 'select_character'):
            w.show_bone_editor()
        result = controller.dispatch(action, **arguments)
        if not isinstance(result, dict):
            raise RuntimeError('The Bone Editor returned an invalid result.')
        return result

    def open_project(self, project_path):
        path = Path(project_path)
        if not path.is_absolute() or str(path).startswith(('\\\\', '//')):
            raise ValueError('Pass an absolute local project directory or project.json path.')
        path = path.resolve(strict=True)
        if str(path).startswith(('\\\\', '//')):
            raise ValueError('Use a local project path.')
        if path.is_file() and path.name.lower() == 'project.json':
            path = path.parent
        if not (path / 'project.json').is_file():
            raise ValueError('No project.json found. Pass a saved RGB MoCap project.')
        self.loaded = False
        self.video_error = self.preview_error = self.scene_error = None
        w = self.window
        if not w.load_project(path):
            raise ValueError(w.status.text())
        self.loaded = True
        return self.status()

    def wait_frame(self):
        w = self.window
        index = w.slider.value()
        self.wait_for(lambda: w.video_view.frame is not None and w.video_view.index == index
                      and w.motion_view.index == index,
                      f'decoded frame {index + 1}', lambda: self.video_error)

    def seek_frame(self, frame):
        w = self.window
        if not self.loaded or not w.info:
            raise ValueError('Open a saved project with video first.')
        if type(frame) is not int or not 1 <= frame <= w.slider.maximum() + 1:
            raise ValueError(f'Frame must be between 1 and {w.slider.maximum() + 1}.')
        w.stop_playback()
        if w.slider.value() == frame - 1:
            w.seek(frame - 1)
        else:
            w.slider.setValue(frame - 1)
        self.wait_frame()
        return self.status()

    def wait_preview(self):
        w = self.window
        signature = project_signature(w.project)
        self.wait_for(lambda: w.preview_data is not None and w.preview_data.signature == signature,
                      'saved motion preview', lambda: self.preview_error)
        if project_signature(w.project) != signature:
            raise RuntimeError('The saved result changed. Reopen the project to inspect it.')

    def wait_scene(self, kind):
        w = self.window
        if w.people_root is not None:
            key = (str(w.people_root), kind)
            self.wait_for(lambda: w.scene_data is not None and w._scene_key == key,
                          'saved person scene', lambda: self.scene_error)

    def image(self, view, label):
        w = self.window
        if view in ('viewport', 'workspace') and not w.motion_view.isValid():
            self.wait_for(w.motion_view.isValid, 'OpenGL viewport')
        if view == 'workspace':
            image = capture_window(w)
        elif view == 'viewport':
            image = w.motion_view.grabFramebuffer()
        elif view == 'video':
            image = w.video_view.grab().toImage()
        else:
            raise ValueError('View must be viewport, workspace, or video.')
        if image.isNull():
            raise RuntimeError('The application returned an empty image.')
        if image.width() > 1440 or image.height() > 1000:
            image = image.scaled(1440, 1000, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        if not buffer.open(QIODevice.WriteOnly) or not image.save(buffer, 'PNG'):
            raise RuntimeError('Could not encode the captured image.')
        buffer.close()
        return {'label': label, 'mimeType': 'image/png', 'data': base64.b64encode(bytes(data)).decode('ascii')}

    def capture_view(self, view='viewport'):
        w = self.window
        if self.loaded and w.info:
            self.wait_frame()
        if self.loaded and w.project and view != 'video':
            self.wait_preview()
            self.wait_scene(w.active_result)
        image = self.image(view, view)
        return {**self.status(), 'view': view,
                'mesh_frame': self.mesh_frame() if view != 'video' else None, 'images': [image]}

    def mesh_frame(self):
        index = self.window.motion_view.mesh_presented_index
        return int(index) + 1 if index is not None else None

    def select_frame_range(self, frame_start=None, frame_end=None):
        w = self.window
        if not self.loaded or not w.info:
            raise ValueError('Open a project before selecting a Timeline range.')
        if frame_start is None and frame_end is None:
            w.slider.clear_export_selection()
        else:
            if (type(frame_start) is not int or type(frame_end) is not int
                    or not 1 <= frame_start <= frame_end <= w.slider.maximum()+1):
                raise ValueError('Provide a frame range within the Timeline.')
            w.stop_playback()
            w.slider.set_export_selection(frame_start-1, frame_end)
        return self.status()

    def export_fbx(self, output_path, frame_start=None, frame_end=None, character_name=None, character_id=None):
        w = self.window
        if not self.loaded or w.project is None:
            raise ValueError('Open a project containing saved motion first.')
        destination = Path(output_path)
        if (not destination.is_absolute() or str(destination).startswith(('\\\\', '//'))
                or destination.suffix.lower() != '.fbx' or destination.is_reserved()
                or ':' in destination.name):
            raise ValueError('Use an absolute local .fbx destination path.')
        parent = destination.parent.resolve(strict=True)
        if not parent.is_dir() or str(parent).startswith(('\\\\', '//')):
            raise ValueError('Choose an existing local destination folder.')
        destination = parent / destination.name

        for project in (w.workspace_root, w.project):
            if project is not None and destination.is_relative_to(Path(project).resolve()):
                raise ValueError('Choose a destination outside the saved project.')
        for root in {HOME, ROOT}:
            app_root = root.resolve()
            if destination.is_relative_to(app_root):
                folder = destination.relative_to(app_root).parts[0].lower()
                if folder.startswith(('runtime', '.')) or folder in {
                    'models', 'projects', 'cache', 'character_scenes', 'config',
                    'installer', 'mocap', 'third_party', 'tools',
                }:
                    raise ValueError('Choose an export folder outside the application data and runtime.')
        if destination.exists() or destination.is_symlink():
            raise FileExistsError('The destination already exists. Choose a new .fbx filename.')
        if frame_start is not None or frame_end is not None:
            limit = w.slider.maximum() + 1
            if (type(frame_start) is not int or type(frame_end) is not int
                    or not 1 <= frame_start <= frame_end <= limit):
                raise ValueError(f'Provide both frame boundaries between 1 and {limit}, inclusive.')
        if character_name is not None or character_id is not None:
            from .character_export_range import export_saved_character_fbx
            return export_saved_character_fbx(w, destination, character_name, frame_start, frame_end,
                                              character_id=character_id)
        from .export_range import export_saved_fbx
        return export_saved_fbx(w, destination, frame_start, frame_end)

    def compare_motion(self, frame):
        w = self.window
        if not self.loaded or w.project is None:
            raise ValueError('Open a project containing original and corrected motion first.')
        self.wait_preview()
        original = base_result(w.active_result)
        corrected = 'corrected_' + original
        for kind in (original, corrected):
            joints = w.preview_data.arrays.get(kind + '_joints')
            if joints is None or not artifacts_current(w.project, kind) or not result_is_current(w.project, kind):
                raise ValueError(f'Saved preview {kind} is missing or outdated. Prepare or apply the correction in RGB MoCap first.')
            if type(frame) is not int or not 1 <= frame <= len(joints):
                raise ValueError(f'Frame is outside the saved motion for {kind}.')
        previous_result, previous_frame = w.active_result, w.slider.value()
        view = w.motion_view
        state = {key: getattr(view, key) for key in ('yaw', 'pitch', 'distance', 'auto_fit', 'follow')}
        state.update(pan=view.pan.copy(), scene_center=view.scene_center.copy())
        signature = w.preview_data.signature
        try:
            self.seek_frame(frame)
            self.wait_scene(previous_result)
            anchor = view.target().copy()
            images = []
            for kind, label in ((original, 'Before correction'), (corrected, 'After correction')):
                self.scene_error = None
                view.auto_fit = False
                w.set_active_result(kind)
                self.wait_scene(kind)
                if project_signature(w.project) != signature or not result_is_current(w.project, kind):
                    raise RuntimeError('The saved motion changed during comparison. Reopen the project and retry.')
                if w.active_result != kind or not w.slider.has_motion or view.index != frame - 1:
                    raise RuntimeError(f'The requested motion and frame are not displayed for {kind}.')
                view.follow = False
                view.yaw, view.pitch, view.distance = state['yaw'], state['pitch'], state['distance']
                view.pan = anchor - view.scene_center
                view.mesh_presented_index = None
                image = self.image('viewport', f'{label} · frame {frame} · {kind}')
                if self.mesh_frame() != frame:
                    raise RuntimeError(f'No saved 3D mesh was rendered for {kind} at frame {frame}. Prepare its preview in RGB MoCap first.')
                images.append(image)
            return {'frame': frame, 'before': original, 'after': corrected,
                    'person_id': w.active_person_id, 'same_camera': True, 'images': images}
        finally:
            w.set_active_result(previous_result)
            w.slider.setValue(previous_frame)
            for key, value in state.items():
                setattr(view, key, value)
            view.update()


def run_session(app):
    output, stream = sys.stdout.buffer, sys.stdin.buffer
    sys.stdout = sys.stderr
    with tempfile.TemporaryDirectory(prefix='rgbmocap-inspection-') as cache:
        os.environ['RGB_MOCAP_INSPECTION_CACHE'] = cache
        window = MainWindow(inspect_only=True)
        window.setWindowTitle('RGB MoCap | Codex inspection')
        window.show()
        inspection = Inspection(app, window, output)
        Thread(target=inspection.read_requests, args=(stream,), daemon=True).start()
        try:
            return app.exec()
        finally:
            inspection.closed = True
            app.removeEventFilter(inspection)
            window.close()
            os.environ.pop('RGB_MOCAP_INSPECTION_CACHE', None)
