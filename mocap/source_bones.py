"""Read the active source person's skeleton for the Bone Editor."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import zipfile

import numpy as np


def _timing(project):
    with (project / 'project.json').open(encoding='utf-8') as stream:
        record = json.load(stream)
    start, fps, frames = float(record.get('start', 0)), float(record['fps']), record['frames']
    if not (math.isfinite(start) and math.isfinite(fps) and fps > 0 and type(frames) is int and frames > 0):
        raise ValueError('Invalid source motion timing.')
    return dict(project=project, start=start, fps=fps, frames=frames)


def source_targets(window):
    """Return source person choices in the same order as the People panel."""
    from .people_store import safe_child

    project = getattr(window, 'project', None)
    if project is None:
        return []
    group = getattr(window, 'people_state', None)
    root = getattr(window, 'people_root', None)
    scene = getattr(window, 'scene_data', None)
    if group and root is not None:
        items = []
        for person in group['people']:
            ident = person['id']
            takes = []
            for take in person.get('takes', []):
                try:
                    path = safe_child(root, take['project'])
                    loaded = scene.by_project.get(path) if scene else None
                    if loaded is not None and loaded.ident == ident:
                        timing = dict(project=path, start=loaded.start, fps=loaded.fps, frames=loaded.frames)
                    else:
                        timing = _timing(path)
                    takes.append(timing)
                except (OSError, KeyError, TypeError, ValueError):
                    continue
            items.append(dict(id=f'source:{ident}', person_id=ident, name=person['name'],
                              source_mode=True, takes=takes))
        return items

    actor = getattr(window, '_single_actor', None)
    if actor is None and not getattr(window, 'preview_data', None):
        return []
    try:
        take = _timing(Path(project).resolve())
    except (OSError, KeyError, TypeError, ValueError):
        take = None
    return [dict(id='source:1', person_id=1, name=actor['name'] if actor else 'Person 1',
                 source_mode=True, takes=[take] if take is not None else [])]


def _person_number(ident):
    if isinstance(ident, str) and ident.startswith('source:'):
        value = ident[7:]
        if value.isascii() and value.isdecimal() and 0 < len(value) <= 10:
            ident = int(value)
    if type(ident) is not int or ident <= 0:
        raise ValueError('Select a source person.')
    return ident


def _active_source(window, ident, index):
    target = next((item for item in source_targets(window) if item['person_id'] == ident), None)
    if target is None:
        raise ValueError('The source person is unavailable.')
    if not target['takes']:
        raise ValueError('Reconstruct this person and prepare its preview first.')
    if type(index) is not int or not 0 <= index < len(target['takes']):
        raise ValueError('Select a valid source take.')
    return target['takes'][index]


def _scene_take(window, ident, project, kind):
    root, scene = getattr(window, 'people_root', None), getattr(window, 'scene_data', None)
    if scene is not None and root is not None and getattr(window, '_scene_key', None) == (str(root), kind):
        take = scene.by_project.get(project)
        if take is not None and take.ident == ident:
            return take
    return None


def _scene_transform(window, project, take):
    if take is not None:
        return np.array(take.transform, copy=True)
    root = getattr(window, 'people_root', None)
    if root is None:
        return np.eye(4)
    from .motion_tools import require_supported_project
    if require_supported_project(project).key == 'flowhmr':
        return np.eye(4)  # FlowHMR already saves the shared world coordinates.
    from .people_store import media_receipt, safe_child
    from .scene_camera import VERSION, read_camera, validate_transform

    try:
        reference_file = root / 'people_scene.json'
        if reference_file.stat().st_size > 1024**2:
            raise ValueError('Scene reference is too large.')
        reference = json.loads(reference_file.read_text(encoding='utf-8'))
        if reference['version'] != VERSION or reference['input'] != media_receipt(root):
            raise ValueError('Scene reference is out of date.')
        anchor = read_camera(safe_child(root, reference['anchor']))
        camera = read_camera(project)
        if anchor is None or camera is None or anchor['sources'] != reference['sources']:
            raise ValueError('Scene camera is out of date.')
        return (np.linalg.inv(validate_transform(reference['world_to_camera']))
                @ validate_transform(camera['world_to_camera']))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError('Prepare the shared scene before inspecting source bones.') from error


def _local_file(project, name):
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError('Invalid source skeleton filename.')
    path = project / name
    if path.resolve() != path:
        raise ValueError('Source skeleton files must be inside the take.')
    return path


def _load_mixamo(project, kind, count):
    """Load only numeric bind arrays and a windowed pose stream."""
    from .preview_data import FrameArray

    receipt = _local_file(project, kind + '_mixamo.json')
    if receipt.stat().st_size > 1024**2:
        raise ValueError('Source skeleton receipt is too large.')
    info = json.loads(receipt.read_text(encoding='utf-8'))
    names = tuple(info['names'])
    if len(names) != 52 or info['frames'] != count:
        raise ValueError('Source skeleton does not match this take.')
    path = _local_file(project, info['asset_file'])
    required = ('rest', 'parents', 'ends')
    optional = 'fbx_display_frames'
    with zipfile.ZipFile(path) as archive:
        entries = archive.namelist()
        for name in required + (optional,):
            entry = name + '.npy'
            if entry in entries and (entries.count(entry) != 1 or archive.getinfo(entry).file_size > 16384):
                raise ValueError('Invalid source skeleton archive.')
    with np.load(path, allow_pickle=False) as archive:
        rest, parents, ends = (archive[name] for name in required)
        display = archive[optional] if optional in archive else np.broadcast_to(np.eye(3), (52, 3, 3))
    deltas = _rest_deltas(rest, parents, ends)
    return names, parents, deltas, display, FrameArray(_local_file(project, info['frames_file']), max_blocks=2)


def _rest_deltas(heads, parents, ends):
    heads, parents, ends = map(np.asarray, (heads, parents, ends))
    n = len(parents)
    if heads.shape != (n, 3) or ends.shape != heads.shape:
        raise ValueError('Invalid source skeleton rest geometry.')
    deltas = ends.astype(float, copy=True)
    for index in range(n):
        children = heads[parents == index]
        if len(children):
            deltas[index] = children.mean(axis=0) - heads[index]
        if np.linalg.norm(deltas[index]) <= .001:
            deltas[index] += (0., .1, 0.)
    return deltas


def _load_soma(project, kind):
    from . import gemx_result
    from .gemx_correct import selected
    from .preview_data import FrameArray
    from .bone_stream import StreamRig

    correction = selected(project) if kind != 'initial' else None
    if kind != 'initial' and correction is None:
        raise ValueError('The corrected source result changed. Prepare Preview again.')
    folder = correction[0] if correction else project
    asset = gemx_result.load_rig(project)
    rest = asset['rest']
    deltas = _rest_deltas(rest[:, :3, 3], asset['parents'], asset['ends'])
    deltas = np.einsum('nji,nj->ni', rest[:, :3, :3], deltas)
    stream = StreamRig.soma(asset)
    return tuple(asset['names'].tolist()), asset['parents'], deltas, stream.display, FrameArray(
        _local_file(folder, gemx_result.POSE), max_blocks=2)


def _borrow_loaded_bones(project, take, preview, kind, native):
    if take is not None and not native:
        from .result_artifacts import file_stat
        if take.target_stamp != file_stat(project / (kind + '_mixamo.json')):
            return None
    arrays = take.arrays if take is not None else getattr(preview, 'arrays', {})
    asset = take.target_asset if take is not None else getattr(preview, 'target_assets', {}).get(kind)
    if not asset or 'bones' not in asset or 'stream_rig' not in asset:
        return None
    stream = asset['stream_rig']
    frames = arrays.get('rig' if take is not None else kind + '_rig')
    if frames is None:
        return None
    names = tuple(row[0] for row in stream.bones)
    parents = np.asarray([row[1] for row in stream.bones])
    deltas = np.asarray([row[2] for row in asset['bones']['segments']])
    return names, parents, deltas, stream.display, frames


@dataclass
class SourceContext:
    project: Path
    kind: str
    start: float
    fps: float
    frames: int
    names: tuple
    parents: tuple
    transform: np.ndarray
    rotations_available: bool
    _matrix_frames: object = field(default=None, repr=False)
    _joints: object = field(default=None, repr=False)
    _rotations: object = field(default=None, repr=False)
    _deltas: object = field(default=None, repr=False)
    _display: object = field(default=None, repr=False)
    _owned: tuple = field(default=(), repr=False)

    def close(self):
        for array in self._owned:
            array.close()
        self._owned = ()

    def frame_at(self, seconds):
        frame = math.floor((seconds - self.start) * self.fps + 1e-6)
        return frame if 0 <= frame < self.frames else None

    def geometry(self, frame):
        if type(frame) is not int or not 0 <= frame < self.frames:
            raise ValueError('Frame is outside this source take.')
        n = len(self.names)
        poses = np.tile(np.eye(4), (n, 1, 1))
        if self._matrix_frames is not None:
            source = self._matrix_frames[frame]
            rotation = source[:, :3, :3]
            heads = source[:, :3, 3]
            tails = heads + np.einsum('nij,nj->ni', rotation, self._deltas)
            poses[:, :3, :3] = rotation @ self._display
        else:
            heads = self._joints[frame]
            if self._rotations is not None:
                poses[:, :3, :3] = self._rotations[frame]
            tails = np.empty_like(heads)
            parents = np.asarray(self.parents)
            for index, head in enumerate(heads):
                children = heads[parents == index]
                if len(children):
                    tails[index] = children.mean(axis=0)
                elif parents[index] >= 0:
                    tails[index] = head + 0.3 * (head - heads[parents[index]])
                else:
                    tails[index] = head + (0., .03, 0.)
        poses[:, :3, 3] = heads
        world = self.transform @ poses
        tails = tails @ self.transform[:3, :3].T + self.transform[:3, 3]
        if not (np.isfinite(world).all() and np.isfinite(tails).all()):
            raise ValueError('Source motion contains invalid bone positions or rotations.')
        return dict(names=self.names, heads=world[:, :3, 3], tails=tails, poses=world,
                    frame=frame, transform=self.transform, rotations_available=self.rotations_available)


def source_context(window, person_id, take_index=0):
    """Read the selected committed result; support canonical, native, or body joints."""
    from .motion_tools import result_is_current, require_supported_project
    from .result_artifacts import artifacts_current
    from .mixamo_data import current as mixamo_current
    from .mixamo_rig import BODY_NAMES, BODY_PARENTS
    from .preview_data import project_signature

    ident = _person_number(person_id)
    timing = _active_source(window, ident, take_index)
    project, frames = timing['project'], timing['frames']
    kind = window.active_result
    if not (result_is_current(project, kind) and artifacts_current(project, kind)):
        raise ValueError('Prepare Preview for the selected source result first.')
    take = _scene_take(window, ident, project, kind)
    preview = getattr(window, 'preview_data', None)
    if preview is not None and (preview.project != project or preview.signature != project_signature(project)):
        preview = None
    transform = _scene_transform(window, project, take)
    native = require_supported_project(project).key == 'gemx'
    canonical = not native and mixamo_current(project, kind)
    if native or canonical:
        payload = _borrow_loaded_bones(project, take, preview, kind, native)
        owned = ()
        if payload is None:
            payload = _load_soma(project, kind) if native else _load_mixamo(project, kind, frames)
            owned = (payload[-1],)
        names, parents, deltas, display, matrix_frames = payload
        n = 77 if native else 52
        try:
            if (len(names) != n or len(set(names)) != n or
                    any(not isinstance(name, str) or not name for name in names) or
                    parents.shape != (n,) or parents.dtype.kind not in 'iu' or
                    parents[0] != -1 or (parents[1:] < 0).any() or
                    (parents[1:] >= np.arange(1, n)).any() or deltas.shape != (n, 3) or
                    display.shape != (n, 3, 3) or matrix_frames.shape != (frames, n, 4, 4) or
                    not np.isfinite(deltas).all() or not np.isfinite(display).all()):
                raise ValueError('Source bone metadata does not match the selected motion.')
        except Exception:
            for array in owned:
                array.close()
            raise
        return SourceContext(**timing, kind=kind, names=names, parents=tuple(map(int, parents)),
                             transform=transform, rotations_available=True,
                             _matrix_frames=matrix_frames, _deltas=deltas, _display=display,
                             _owned=owned)

    arrays = take.arrays if take is not None else getattr(preview, 'arrays', {})
    prefix = '' if take is not None else kind + '_'
    joints, rotations = arrays.get(prefix + 'joints'), arrays.get(prefix + 'rotations')
    if joints is None or joints.shape != (frames, 22, 3):
        raise ValueError('Prepare Preview to load the source skeleton.')
    if rotations is not None and rotations.shape != (frames, 22, 3, 3):
        raise ValueError('Source rotations do not match the selected motion.')
    return SourceContext(**timing, kind=kind, names=BODY_NAMES, parents=BODY_PARENTS,
                         transform=transform, rotations_available=rotations is not None,
                         _joints=joints, _rotations=rotations)
