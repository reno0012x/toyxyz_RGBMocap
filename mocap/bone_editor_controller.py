"""Character-only animation layers shared by native controls and MCP."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import json
from pathlib import Path
import time
import uuid
import warnings

import numpy as np
from PySide6.QtCore import QObject, QEventLoop, QTimer, Qt

from .storage import atomic_json
from .preview_data import FrameArray
from .i18n import tr


class BoneEditorController(QObject):
    def __init__(self, window, widget):
        super().__init__(window)
        self.window, self.widget = window, widget
        self.character_id = None
        self.take_index = 0
        self.bone = None
        self.frame = 0
        self.tool = 'rotate'
        self.xray = True
        self.contexts = OrderedDict()
        self.pending = None
        self.preparation_error = None
        self._character_signature = None
        self._syncing = False
        self._draft = None
        self._drag = None
        self._widget_signature = None
        self._widget_context = None
        self._widget_layer = None
        self._source_cache = None
        self._source_target_cache = None
        widget.action_requested.connect(self._ui_action)
        window.slider.valueChanged.connect(self.sync_time)
        window.people_list.itemClicked.connect(self.sync_people_selection)
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def _ui_action(self, action, arguments):
        try:
            self.dispatch(action, **dict(arguments or {}))
        except Exception as error:
            self.window.status.setText(str(error))
            self.widget.set_busy(False, str(error))

    def _characters(self):
        return getattr(self.window, 'characters', [])

    def _targets(self):
        from .source_bones import source_targets
        w = self.window
        group = getattr(w, 'people_state', None) or {}
        people = tuple((p['id'], p['name'], tuple(t['project'] for t in p.get('takes', [])))
                       for p in group.get('people', []))
        single = getattr(w, '_single_actor', None) or {}
        key = (w.project, id(w.scene_data), id(w.preview_data), people, single.get('name'))
        if self._source_target_cache is None or self._source_target_cache[0] != key:
            self._source_target_cache = key, source_targets(w)
        return self._source_target_cache[1] + self._characters()

    @property
    def source_mode(self):
        return bool(self.character_id and self.character_id.startswith('source:'))

    def is_active(self):
        active = getattr(self.window, 'bone_editor_is_active', None)
        return bool(active()) if active else self.widget.isVisible()

    def focused_person(self):
        if self.is_active() and self.source_mode:
            return int(self.character_id.split(':', 1)[1])
        return None

    def focuses_character(self):
        return self.is_active() and not self.source_mode and bool(self.character_id)

    def sync_people_selection(self, item=None):
        """The active Bone Editor follows an explicit People-list selection."""
        if not self.is_active() or self.window.busy or self.window.contact_saving:
            return
        item = self.window.people_list.currentItem() if item is None else item
        if item is None:
            return
        value = item if isinstance(item, (int, str)) else item.data(Qt.UserRole)
        if type(value) is int and value > 0:
            ident = f'source:{value}'
        elif isinstance(value, str) and value.startswith('character:'):
            ident = value.removeprefix('character:')
        else:
            return
        if ident != self.character_id and any(t['id'] == ident for t in self._targets()):
            self._ui_action('select_character', {'character_id': ident, 'take_index': 0})

    def _source_context(self, required=True):
        from .source_bones import source_context
        w = self.window
        key = (self.character_id, self.take_index, w.project, w.active_result,
               id(w.scene_data), id(w.preview_data))
        if self._source_cache is not None and self._source_cache[0] != key:
            self._source_cache[1].close()
            self._source_cache = None
        if self._source_cache is None:
            try:
                source = source_context(w, self.character_id, self.take_index)
            except (OSError, ValueError, KeyError, RuntimeError):
                if required:
                    raise
                return None
            self._source_cache = key, source
        return self._source_cache[1]

    def _character(self, ident=None):
        ident = ident if ident is not None else self.character_id
        matches = [c for c in self._characters() if c['id'] == ident]
        if len(matches) != 1:
            raise ValueError('Select an imported character with retargeted motion.')
        c = matches[0]
        if not c.get('takes') or not c.get('animation'):
            raise ValueError('Retarget the character before editing its bones.')
        if c.get('needs_retarget'):
            raise ValueError('Retarget the character again before editing its bones.')
        return c

    def _base_folder(self, c, index=None):
        index = self.take_index if index is None else index
        if type(index) is not int or not 0 <= index < len(c.get('takes', [])):
            raise ValueError('Select a valid character take.')
        take = c['takes'][index]
        folder = self.window.character_path(c['animation'] + '/' + take['folder'])
        return folder, take

    def _context(self, c=None, index=None, required=True):
        from .bone_animation import base_identity_for, empty_layer, validate_layer
        c = c or self._character()
        index = self.take_index if index is None else index
        base, take = self._base_folder(c, index)
        key = str(base)
        identity = base_identity_for(base)
        existing = self.contexts.get(key)
        if existing is not None and existing['identity'] == identity:
            self.contexts.move_to_end(key)
            return existing
        link = base / 'bone-editor-cache.json'
        if not link.is_file():
            if required:
                raise ValueError('Prepare the Bone Editor for this character first.')
            return None
        record = json.loads(link.read_text(encoding='utf-8'))
        name = record.get('folder', '')
        if not name or Path(name).name != name or record.get('base_identity') != identity:
            if required:
                raise ValueError('Prepare the Bone Editor again for the current animation.')
            return None
        cache = base / name
        if not cache.resolve().is_relative_to(base.resolve()):
            raise ValueError('Invalid bone editor cache location.')
        required_files = ('bone-editor.json', 'bone-skeleton.npz', 'preview-frames.npy', 'preview.npz')
        if not all((cache / name).is_file() for name in required_files):
            if required:
                raise ValueError('Prepare the Bone Editor again to rebuild its missing preview files.')
            return None
        info = json.loads((cache / 'bone-editor.json').read_text(encoding='utf-8'))
        if info['base_identity'] != identity or int(info['frames']) != take['frames']:
            raise ValueError('Bone editor cache does not match this animation.')
        with np.load(cache / 'bone-skeleton.npz', allow_pickle=False) as archive:
            skeleton = {name: archive[name].copy() for name in ('names', 'parents', 'rest', 'tails')}
        names = skeleton['names'].tolist()
        frames = int(info['frames'])
        path = base / 'bone-edits.json'
        if path.exists():
            if path.stat().st_size > 8 * 1024 ** 2:
                raise ValueError('Bone edit layer exceeds the size limit.')
            layer = validate_layer(json.loads(path.read_text(encoding='utf-8')),
                                   names=names, frames=frames, base_identity=identity)
        else:
            layer = empty_layer(identity, frames)
        context = dict(base=base, cache=cache, identity=identity, take=take, frames=frames,
                       names=names, skeleton=skeleton, layer=layer, undo=[], redo=[],
                       array=FrameArray(cache / 'preview-frames.npy', max_blocks=2), revision=0,
                       edited_frame=None, edited_palette=None, path=path,
                       stamp=self._stamp(path))
        self.contexts[key] = context
        while len(self.contexts) > 8:
            _, old = self.contexts.popitem(last=False)
            old['array'].close()
        if existing is not None:
            existing['array'].close()
        return context

    @staticmethod
    def _stamp(path):
        return (path.stat().st_size, path.stat().st_mtime_ns) if path.exists() else None

    def refresh(self):
        if self._syncing:
            return
        try:
            characters = self._targets()
            signature = (str(getattr(self.window, 'character_root', None)),
                         tuple((c['id'], c['name'], c.get('animation'),
                                tuple((t.get('start'), t.get('fps'), t.get('frames')) for t in c.get('takes', [])),
                                bool(c.get('needs_retarget')), c.get('visible')) for c in characters),
                         id(self.window.scene_data), id(self.window.preview_data), self.window.active_result)
            if signature != self._character_signature:
                self._character_signature = signature
                self.widget.set_characters(characters)
                if not any(c['id'] == self.character_id for c in characters):
                    chosen = next((c for c in characters if c.get('source_mode') and c.get('takes')), None)
                    chosen = chosen or next((c for c in characters if c.get('takes') and c.get('visible')), None)
                    chosen = chosen or next((c for c in characters if c.get('takes')), None)
                    chosen = chosen or next(iter(characters), None)
                    self.character_id = chosen['id'] if chosen else None
                    self.take_index = 0
                    self.bone = None
            busy = bool(self.window.busy)
            if self.is_active() and (signature, busy) != self._widget_signature:
                self._widget_signature = (signature, busy)
                self._update_widget()
        except Exception as error:
            self.widget.set_busy(False, str(error))

    def _update_widget(self):
        self._syncing = True
        try:
            state = self.status()
            if self.source_mode:
                source = self._source_context(required=False)
                if self._widget_context is not source:
                    self.widget.set_skeleton(list(source.names) if source else [], list(source.parents) if source else [])
                    self.widget.set_layer({'enabled': True, 'tracks': {}})
                self._widget_context, self._widget_layer = source, None
                if source:
                    if self.bone not in source.names:
                        self.bone = source.names[0]
                    state.update(self._source_pose(source, self.bone, min(self.frame + 1, source.frames)))
                self.widget.set_state(state)
                self.widget.set_busy(bool(self.window.busy))
                return
            context = self._context(required=False) if state['character_id'] and state['retargeted'] else None
            if context is not None:
                if context is not self._widget_context:
                    self.widget.set_skeleton(context['names'], context['skeleton']['parents'].tolist())
                if context['layer'] is not self._widget_layer:
                    self.widget.set_layer(context['layer'])
                if self.bone not in context['names']:
                    self.bone = context['names'][0]
                state.update(self.get_pose(context=context))
            elif self._widget_context is not None:
                self.widget.set_skeleton([], [])
                self.widget.set_layer({'enabled': True, 'tracks': {}})
            self._widget_context = context
            self._widget_layer = context['layer'] if context is not None else None
            self.widget.set_state(state)
            self.widget.set_busy(bool(self.window.busy), self.preparation_error or
                                 (tr('Preparing Bone Editor...') if self.pending else ''))
        finally:
            self._syncing = False

    def status(self):
        characters = self._targets()
        c = next((c for c in characters if c['id'] == self.character_id), None)
        if self.source_mode:
            source = self._source_context(required=False)
            frames = source.frames if source else 1
            return dict(character_id=self.character_id, take_index=self.take_index, bone=self.bone,
                        frame=min(self.frame + 1, frames), frames=frames, source_mode=True,
                        ready=source is not None, retargeted=False, enabled=True, can_undo=False, can_redo=False,
                        tool='select', xray=self.xray, selection=None,
                        status=tr('Source motion · view only') if source else tr('Prepare the source motion preview first.'),
                        characters=self._target_summaries(characters))
        retargeted = bool(c and c.get('takes') and not c.get('needs_retarget'))
        context = self._context(c, required=False) if retargeted else None
        frames = context['frames'] if context else (c['takes'][self.take_index]['frames']
                  if retargeted and self.take_index < len(c['takes']) else 1)
        status_text = 'Select a bone to edit.' if context else 'Prepare the Bone Editor to edit this take.'
        if c and not c.get('visible', True):
            status_text = 'Check this character in People to show it in the viewport.'
        return dict(character_id=self.character_id, take_index=self.take_index, bone=self.bone, source_mode=False,
                    frame=min(self.frame + 1, frames), frames=frames, ready=context is not None,
                    retargeted=retargeted, enabled=context['layer']['enabled'] if context else True,
                    can_undo=bool(context and context['undo']), can_redo=bool(context and context['redo']),
                    tool=self.tool, xray=self.xray, selection=self._selection(),
                    status=tr(status_text),
                    characters=self._target_summaries(characters))

    @staticmethod
    def _target_summaries(targets):
        return [dict(id=c['id'], name=c['name'], takes=len(c.get('takes', [])),
                     source_mode=bool(c.get('source_mode'))) for c in targets]

    def _selection(self):
        selected = self.window.slider.export_selection
        if selected is None:
            return None
        try:
            c = self._character()
            _, take = self._base_folder(c)
            fps = self.window.info['fps']
            start = self.window.source_offset
            first = round((start + selected[0] / fps - take['start']) * take['fps'])
            last = round((start + (selected[1] - 1) / fps - take['start']) * take['fps'])
            if first > last or last < 0 or first >= take['frames']:
                return None
            return [max(0, first) + 1, min(take['frames'] - 1, last) + 1]
        except (ValueError, TypeError, KeyError):
            return None

    def sync_time(self, *_):
        if self.window.info:
            try:
                if self.source_mode:
                    source = self._source_context()
                    take = dict(start=source.start, fps=source.fps, frames=source.frames)
                else:
                    _, take = self._base_folder(self._character())
                seconds = self.window.source_offset + self.window.slider.value() / self.window.info['fps']
                self.frame = max(0, min(take['frames'] - 1, round((seconds - take['start']) * take['fps'])))
            except (OSError, ValueError, KeyError, RuntimeError):
                pass
        if self.is_active():
            self._update_widget()

    def seek(self, frame):
        if self.source_mode:
            source = self._source_context()
            take = dict(start=source.start, fps=source.fps, frames=source.frames)
        else:
            take = self._context()['take']
        if type(frame) is not int or not 1 <= frame <= take['frames']:
            raise ValueError('Frame is outside the selected character take.')
        self.window.stop_playback()
        self.frame = frame - 1
        if self.window.info:
            seconds = take['start'] + self.frame / take['fps'] - self.window.source_offset
            self.window.slider.setValue(max(0, min(self.window.slider.maximum(),
                                        round(seconds * self.window.info['fps']))))
        self._update_widget()
        self.window.motion_view.update()

    def prepare(self, wait=False):
        from .bone_animation import base_identity_for
        if self.pending is None:
            if self.window.busy or self.window.contact_saving:
                raise RuntimeError('Wait for the current processing job to finish.')
            c = self._character()
            base, _ = self._base_folder(c)
            if self._context(c, required=False) is not None:
                return self.status()
            cache = base / ('be-' + uuid.uuid4().hex[:10])
            identity = base_identity_for(base)
            job = dict(mode='bone_editor_prepare', output=str(cache), animation=str(base),
                       bone_character_id=c['id'], bone_take_index=self.take_index,
                       bone_base_identity=identity)
            self.pending = job
            self.preparation_error = None
            self.window.start_character_job(job)
            if self.window.character_process is None:
                self.pending = None
                raise RuntimeError(self.window.status.text())
        if wait:
            deadline = time.monotonic() + 180
            while self.pending is not None:
                if time.monotonic() > deadline:
                    raise TimeoutError('Bone Editor preparation is still running. Check its status before retrying.')
                loop = QEventLoop()
                QTimer.singleShot(25, loop.quit)
                loop.exec()
            if self.preparation_error:
                raise RuntimeError(self.preparation_error)
        self._update_widget()
        return self.status()

    def prepared(self, job, succeeded):
        if job.get('mode') != 'bone_editor_prepare':
            return
        self.pending = None
        if not succeeded:
            self.preparation_error = 'Bone Editor preparation failed. See Console.'
        else:
            try:
                base = Path(job['animation'])
                cache = Path(job['output'])
                info = json.loads((cache / 'bone-editor.json').read_text(encoding='utf-8'))
                if info['base_identity'] != job['bone_base_identity']:
                    raise ValueError('Animation changed while preparing the Bone Editor.')
                atomic_json(base / 'bone-editor-cache.json',
                            dict(folder=cache.name, base_identity=info['base_identity']))
                self.character_id = job['bone_character_id']
                self.take_index = job['bone_take_index']
                context = self._context()
                self.bone = self.bone if self.bone in context['names'] else context['names'][0]
                self.window.character_loader.request(cache, self.frame,
                    self.window.character_path(self._character()['asset']))
            except Exception as error:
                self.preparation_error = str(error)
        if self.preparation_error:
            self.window.status.setText(self.preparation_error)
        self._update_widget()
        self.window.motion_view.update()

    def _check_editable(self):
        if self.window.busy or self.window.contact_saving or getattr(self.window, '_pear_active', False):
            raise RuntimeError('Wait for processing to finish before editing character bones.')
        self.window.stop_playback()
        context = self._context()
        if self._stamp(context['path']) != context['stamp']:
            raise RuntimeError('Bone edits changed in another session. Reopen this character before editing.')
        return context

    def _commit(self, context, layer, history=True):
        from .bone_animation import validate_layer
        layer = validate_layer(layer, names=context['names'], frames=context['frames'],
                               base_identity=context['identity'])
        before = deepcopy(context['layer'])
        if before == layer:
            return
        atomic_json(context['path'], layer)
        if history:
            context['undo'].append(before)
            context['undo'] = context['undo'][-100:]
            context['redo'].clear()
        context['layer'] = layer
        context['stamp'] = self._stamp(context['path'])
        context['revision'] += 1
        context['edited_frame'] = None
        self._draft = None
        self._update_widget()
        self.window.motion_view.update()

    def get_pose(self, bone=None, frame=None, context=None):
        from .bone_animation import sample_offset
        from scipy.spatial.transform import Rotation
        context = context or self._context()
        name = bone or self.bone or context['names'][0]
        if name not in context['names']:
            raise ValueError('Unknown character bone: ' + str(name))
        frame = self.frame + 1 if frame is None else frame
        if type(frame) is not int or not 1 <= frame <= context['frames']:
            raise ValueError('Frame is outside the selected character take.')
        track = context['layer']['tracks'].get(name)
        offset = sample_offset(track, frame - 1) if track else np.eye(4)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            angles = Rotation.from_matrix(offset[:3, :3]).as_euler('xyz', degrees=True).tolist()
        sk = context['skeleton']
        palette = context['array'][frame - 1]
        edited = self.draw_palette(context, palette, frame - 1)
        index = context['names'].index(name)
        base_pose = palette[index] @ sk['rest'][index]
        pose = edited[index] @ sk['rest'][index]
        placement = context['take'].get('transform')
        if placement is not None:
            pose = np.asarray(placement) @ pose
            base_pose = np.asarray(placement) @ base_pose
        return dict(bone=name, frame=frame, frames=context['frames'],
                    translation=offset[:3, 3].tolist(), rotation=angles,
                    space=track.get('space', 'local') if track else 'local',
                    world_position=pose[:3, 3].tolist(), world_matrix=pose.tolist(),
                    base_world_position=base_pose[:3, 3].tolist(), base_world_matrix=base_pose.tolist(),
                    keyframes=[k['frame'] + 1 for k in track['keys']] if track else [])

    def dispatch(self, action, **arguments):
        from . import bone_animation as engine
        if action == 'search_memory':
            from .motion_memory_tools import search
            return dict(examples=search(self.window, **arguments))
        if action == 'forget_motion':
            from .motion_memory import delete_example
            from .motion_memory_tools import workspace_root
            return dict(deleted=delete_example(workspace_root(self.window), arguments['example_id']))
        if arguments.get('character_id') is not None:
            ident = arguments.pop('character_id')
            if not any(c['id'] == ident for c in self._targets()):
                raise ValueError('Unknown motion target ID.')
            if ident != self.character_id:
                self.take_index = 0
                self.bone = None
            self.character_id = ident
        if arguments.get('take_index') is not None:
            index = arguments.pop('take_index')
            if self.source_mode:
                target = next(c for c in self._targets() if c['id'] == self.character_id)
                if type(index) is not int or not 0 <= index < max(1, len(target['takes'])):
                    raise ValueError('Select a valid source take.')
            elif action != 'select_character' or any(c['id'] == self.character_id and c.get('takes') for c in self._characters()):
                self._base_folder(self._character(), index)
            if index != self.take_index:
                self.bone = None
            self.take_index = index
        if action == 'status':
            self.refresh()
            return self.status()
        if action == 'select_character':
            self.bone = None
            self.frame = 0
            self.preparation_error = None
            self.sync_time()
            if self.is_active() and self.window.info and self.character_id:
                target = next(c for c in self._targets() if c['id'] == self.character_id)
                if target.get('takes'):
                    take = target['takes'][self.take_index]
                    instant = self.window.source_offset + self.window.slider.value() / self.window.info['fps']
                    if not take['start'] <= instant < take['start'] + take['frames'] / take['fps']:
                        self.window.stop_playback()
                        frame = round((take['start'] - self.window.source_offset) * self.window.info['fps'])
                        self.window.slider.setValue(max(0, min(frame, self.window.slider.maximum())))
            self._update_widget()
            self.window.update_readiness()
            self.window.motion_view.update()
            return self.status()
        if action == 'prepare':
            if self.source_mode:
                raise ValueError('Use Prepare Preview for source motion. Retarget to edit bones.')
            return self.prepare(wait=bool(arguments.get('wait', False)))
        if action in ('set_tool', 'set_xray'):
            if action == 'set_tool':
                if arguments['tool'] not in ('select', 'translate', 'rotate'):
                    raise ValueError('Choose a valid bone editing tool.')
                self.tool = arguments['tool']
            else:
                if type(arguments['enabled']) is not bool:
                    raise ValueError('X-Ray requires a boolean value.')
                self.xray = arguments['enabled']
            self._update_widget()
            self.window.motion_view.update()
            return self.status()
        if action == 'analyze_motion':
            from .motion_memory_tools import analyze
            return analyze(self, **arguments)
        if action == 'remember_motion':
            from .motion_memory_tools import remember
            return remember(self, **arguments)
        if self.source_mode:
            return self._source_action(action, arguments)
        if self._context(required=False) is None:
            if action == 'list_bones' and not arguments.get('prepare', True):
                return dict(self.status(), bones=[])
            self.prepare(wait=True)
        context = self._context()
        if action == 'list_bones':
            return dict(character_id=self.character_id, take_index=self.take_index,
                        frames=context['frames'], bones=[dict(name=name,
                            parent=context['names'][int(context['skeleton']['parents'][i])]
                            if context['skeleton']['parents'][i] >= 0 else None,
                            keyframes=[k['frame'] + 1 for k in context['layer']['tracks'].get(name, {}).get('keys', [])])
                            for i, name in enumerate(context['names'])])
        if action == 'select_bone':
            if arguments['bone'] not in context['names']:
                raise ValueError('Unknown character bone: ' + str(arguments['bone']))
            self.bone = arguments['bone']
            self._update_widget()
            self.window.motion_view.update()
            return self.get_pose()
        if action == 'get_pose':
            return self.get_pose(arguments.get('bone'), arguments.get('frame'))
        if action == 'seek':
            self.seek(arguments['frame'])
            return self.status()
        if action == 'save':
            context = self._check_editable()
            atomic_json(context['path'], context['layer'])
            context['stamp'] = self._stamp(context['path'])
            return dict(saved=True, path=str(context['path']))
        context = self._check_editable()
        layer = context['layer']
        name = arguments.get('bone', self.bone)
        if action in ('set_keyframe', 'delete_keyframe', 'move_keyframe', 'set_range', 'clear_track'):
            if name not in context['names']:
                raise ValueError('Select a valid character bone.')
            self.bone = name
        if action in ('set_keyframe', 'set_range'):
            values = dict(translation=arguments.get('translation', [0., 0., 0.]),
                          rotation=arguments.get('rotation', [0., 0., 0.]),
                          space=arguments.get('space', 'local'))
            if action == 'set_keyframe':
                frame = arguments.get('frame', self.frame + 1)
                if type(frame) is not int:
                    raise ValueError('Frame must be an integer.')
                changed = engine.set_keyframe(layer, name, frame - 1, **values)
            else:
                first, last = arguments['frame_start'], arguments['frame_end']
                if type(first) is not int or type(last) is not int:
                    raise ValueError('Frame boundaries must be integers.')
                changed = engine.set_range(layer, name, first - 1, last - 1, **values)
        elif action == 'delete_keyframe':
            changed = engine.delete_keyframe(layer, name, arguments['frame'] - 1)
        elif action == 'move_keyframe':
            changed = engine.move_keyframe(layer, name, arguments['frame'] - 1, arguments['new_frame'] - 1)
        elif action == 'clear_track':
            changed = deepcopy(layer)
            changed['tracks'].pop(name, None)
        elif action == 'set_enabled':
            if type(arguments['enabled']) is not bool:
                raise ValueError('Layer enabled requires a boolean value.')
            changed = deepcopy(layer)
            changed['enabled'] = arguments['enabled']
        elif action in ('undo', 'redo'):
            source, destination = ('undo', 'redo') if action == 'undo' else ('redo', 'undo')
            if context[source]:
                changed = context[source][-1]
                self._commit(context, changed, history=False)
                context[source].pop()
                context[destination].append(deepcopy(layer))
                self._update_widget()
            return self.status()
        else:
            raise ValueError('Unknown bone editor action: ' + str(action))
        self._commit(context, changed)
        return dict(self.status(), pose=self.get_pose() if self.bone else None)

    def _source_pose(self, source, name, frame):
        if type(frame) is not int or not 1 <= frame <= source.frames:
            raise ValueError('Frame is outside the selected source take.')
        if name not in source.names:
            raise ValueError('Unknown source bone: ' + str(name))
        geometry = source.geometry(frame - 1)
        matrix = geometry['poses'][source.names.index(name)]
        return dict(bone=name, frame=frame, frames=source.frames, source_mode=True,
                    world_matrix=matrix.tolist() if geometry.get('rotations_available') else None,
                    world_position=matrix[:3, 3].tolist(), keyframes=[])

    def _source_action(self, action, arguments):
        if action not in ('list_bones', 'select_bone', 'get_pose', 'seek'):
            raise ValueError('Source bones are view only. Select a retargeted character to edit bones.')
        source = self._source_context()
        if action == 'list_bones':
            return dict(character_id=self.character_id, take_index=self.take_index,
                        frames=source.frames, source_mode=True,
                        bones=[dict(name=name, parent=source.names[parent] if parent >= 0 else None,
                                    keyframes=[]) for name, parent in zip(source.names, source.parents)])
        if action == 'seek':
            self.seek(arguments['frame'])
            return self.status()
        name = arguments.get('bone') or self.bone or source.names[0]
        pose = self._source_pose(source, name, arguments.get('frame', min(self.frame + 1, source.frames)))
        if action == 'select_bone':
            self.bone = name
            self._update_widget()
            self.window.motion_view.update()
        return pose

    def draw_context(self, c, take):
        try:
            index = next(i for i, t in enumerate(c.get('takes', [])) if t is take)
            base, _ = self._base_folder(c, index)
            if str(base) not in self.contexts and not (base / 'bone-editor-cache.json').is_file():
                return None
            context = self._context(c, index, required=False)
            if context is None:
                return None
            layer = context['layer']
            if layer['enabled'] and layer['tracks'] or (self.is_active() and
                    (c['id'], index) == (self.character_id, self.take_index)):
                return context
        except (ValueError, OSError, KeyError, StopIteration):
            return None

    def draw_palette(self, context, palette, frame):
        from .bone_animation import apply_layer
        layer = self._draft if self._draft is not None and self._drag and context is self._drag[0] else context['layer']
        key = (frame, context['revision'], id(layer))
        if context['edited_frame'] != key:
            sk = context['skeleton']
            context['edited_palette'] = apply_layer(palette, sk['rest'], sk['parents'], context['names'], layer, frame)
            context['edited_frame'] = key
        return context['edited_palette']

    def begin_drag(self):
        try:
            context = self._check_editable()
            values = self.get_pose(context=context)
            if not context['layer']['enabled']:
                raise ValueError('Enable the edit layer before using the transform handles.')
            if not values['keyframes']:
                values['space'] = self.widget.space.currentData()
            self._drag = (context, values, values)
            return True
        except Exception as error:
            self.window.status.setText(str(error))
            return False

    def preview_drag(self, axis, delta):
        from .bone_animation import set_keyframe
        if self._drag:
            context, original, _ = self._drag
            values = deepcopy(original)
            channel = 'translation' if self.tool == 'translate' else 'rotation'
            values[channel][axis] += delta
            self._draft = set_keyframe(context['layer'], values['bone'], values['frame'] - 1,
                                       values['translation'], values['rotation'], values['space'])
            self._drag = (context, original, values)
            context['edited_frame'] = None
            self.window.motion_view.update()

    def finish_drag(self):
        if not self._drag:
            return
        context, original, values = self._drag
        self._drag = None
        self._draft = None
        context['edited_frame'] = None
        if original != values:
            args = {key: values[key] for key in ('bone', 'frame', 'translation', 'rotation', 'space')}
            self._ui_action('set_keyframe', args)
        self.window.motion_view.update()

    def current_geometry(self):
        try:
            if self.source_mode:
                source = self._source_context(required=False)
                if source is None:
                    return None
                frame = int((self.window.motion_view.scene_time - source.start) * source.fps + 1e-6)
                return source.geometry(frame) if 0 <= frame < source.frames else None
            context = self._context(required=False)
            if context is None:
                return None
            c = self._character()
            take = context['take']
            t = self.window.motion_view.scene_time
            frame = int((t - take['start']) * take['fps'] + 1e-6)
            if not 0 <= frame < context['frames'] or not (c.get('visible', True) or self.edit_preview(c)):
                return None
            palette = self.draw_palette(context, context['array'][frame], frame)
            sk = context['skeleton']
            poses = palette[:-1] @ sk['rest']
            heads = poses[:, :3, 3]
            homogeneous = np.column_stack((sk['tails'], np.ones(len(heads))))
            tails = np.einsum('nij,nj->ni', palette[:-1], homogeneous)[:, :3]
            transform = take.get('transform')
            if transform is not None:
                matrix = np.asarray(transform)
                heads = heads @ matrix[:3, :3].T + matrix[:3, 3]
                tails = tails @ matrix[:3, :3].T + matrix[:3, 3]
                poses = matrix @ poses
            return dict(context=context, names=context['names'], heads=heads, tails=tails,
                        poses=poses, frame=frame, transform=transform)
        except (ValueError, OSError, KeyError, RuntimeError):
            return None

    def close(self):
        self.timer.stop()
        for context in self.contexts.values():
            context['array'].close()
        self.contexts.clear()
        if self._source_cache is not None:
            self._source_cache[1].close()
            self._source_cache = None

    def edit_preview(self, character):
        return self.focuses_character() and character['id'] == self.character_id and bool(character.get('visible', True))
