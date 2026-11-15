"""Versioned, non-destructive bone offsets shared by preview and Blender export.

Frames in this module are zero-based take samples. Translation is metres and
rotation is extrinsic XYZ degrees (Rz @ Ry @ Rx), in local posed-bone or world
axes. The source skeleton, skin bind and animation are never modified here.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np


VERSION = 1
MAX_BONES = 4096
MAX_KEYS = 200000


def _integer(value, name, low=0):
    if type(value) is not int or value < low:
        raise ValueError(name + ' must be an integer >= ' + str(low) + '.')
    return value


def _vector(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(name + ' must contain three finite numbers.')
    if any(type(v) not in (int, float) for v in value):
        raise ValueError(name + ' must contain three finite numbers.')
    result = [float(v) for v in value]
    if not np.isfinite(result).all() or max(abs(v) for v in result) > 1e8:
        raise ValueError(name + ' contains an invalid value.')
    return result


def empty_layer(base_identity, frames):
    return validate_layer(dict(version=VERSION, base_identity=base_identity,
                               frames=frames, enabled=True, tracks={}))


def validate_layer(layer, names=None, frames=None, base_identity=None):
    """Return a detached normalized layer, rejecting stale or invalid input."""
    if not isinstance(layer, dict) or layer.get('version') != VERSION:
        raise ValueError('Unsupported bone edit layer version.')
    identity = layer.get('base_identity')
    if not isinstance(identity, str) or not identity or len(identity) > 256:
        raise ValueError('A bone edit layer requires its base animation identity.')
    count = _integer(layer.get('frames'), 'Frame count', 1)
    if frames is not None and count != frames:
        raise ValueError('Bone edits belong to a different animation duration.')
    if base_identity is not None and identity != base_identity:
        raise ValueError('Bone edits belong to an older animation. Restore or reset the layer first.')
    if type(layer.get('enabled')) is not bool:
        raise ValueError('Bone layer enabled must be a boolean.')
    tracks = layer.get('tracks')
    if not isinstance(tracks, dict) or len(tracks) > MAX_BONES:
        raise ValueError('Invalid bone edit tracks.')
    allowed = None if names is None else set(map(str, names))
    normalized = {}
    total = 0
    for name, track in tracks.items():
        if not isinstance(name, str) or not name or len(name) > 512:
            raise ValueError('Invalid bone name.')
        if allowed is not None and name not in allowed:
            raise ValueError('The skeleton does not contain bone: ' + name)
        if not isinstance(track, dict) or track.get('space') not in ('local', 'world'):
            raise ValueError('Bone edit space must be local or world.')
        keys = track.get('keys')
        if not isinstance(keys, list):
            raise ValueError('Bone keyframes must be a list.')
        total += len(keys)
        if total > MAX_KEYS:
            raise ValueError('Bone layer exceeds the keyframe limit.')
        seen = set()
        clean = []
        for key in keys:
            if not isinstance(key, dict):
                raise ValueError('Invalid bone keyframe.')
            frame = _integer(key.get('frame'), 'Keyframe')
            if frame >= count or frame in seen:
                raise ValueError('Bone keyframes must be unique and inside the animation.')
            seen.add(frame)
            clean.append(dict(frame=frame,
                              translation=_vector(key.get('translation'), 'Translation'),
                              rotation=_vector(key.get('rotation'), 'Rotation')))
        if clean:
            normalized[name] = dict(space=track['space'], keys=sorted(clean, key=lambda k: k['frame']))
    return dict(version=VERSION, base_identity=identity, frames=count,
                enabled=layer['enabled'], tracks=normalized)


def base_identity_for(folder):
    """Path-independent source generation; shutil.copy2 project saves retain it."""
    folder = Path(folder)
    entries = []
    for name in ('animation.blend', 'import.json', 'bake.json'):
        value = (folder / name).stat()
        entries.append((name, value.st_size, value.st_mtime_ns))
    return hashlib.sha256(repr(entries).encode('utf-8')).hexdigest()


def load_export_layer(folder):
    """Read an optional committed layer and fail loudly if its base changed."""
    folder = Path(folder)
    path = folder / 'bone-edits.json'
    if not path.is_file():
        return None
    if path.stat().st_size > 32 * 1024 ** 2:
        raise ValueError('Bone edit layer exceeds the size limit.')
    layer = json.loads(path.read_text(encoding='utf-8'))
    info = json.loads((folder / 'bake.json').read_text(encoding='utf-8'))
    return validate_layer(layer, frames=info['frames'], base_identity=base_identity_for(folder))


def set_keyframe(layer, bone, frame, translation=(0, 0, 0), rotation=(0, 0, 0), space='local'):
    result = validate_layer(layer)
    _integer(frame, 'Keyframe')
    track = result['tracks'].get(bone)
    if track and track['space'] != space:
        raise ValueError('Clear this bone track before changing its coordinate space.')
    keys = [] if track is None else [k for k in track['keys'] if k['frame'] != frame]
    keys.append(dict(frame=frame, translation=list(translation), rotation=list(rotation)))
    result['tracks'][bone] = dict(space=space, keys=keys)
    return validate_layer(result)


def delete_keyframe(layer, bone, frame):
    result = validate_layer(layer)
    _integer(frame, 'Keyframe')
    if bone in result['tracks']:
        result['tracks'][bone]['keys'] = [k for k in result['tracks'][bone]['keys'] if k['frame'] != frame]
    return validate_layer(result)


def move_keyframe(layer, bone, frame, new_frame):
    result = validate_layer(layer)
    _integer(frame, 'Keyframe')
    _integer(new_frame, 'New keyframe')
    keys = result['tracks'].get(bone, {}).get('keys', [])
    selected = next((k for k in keys if k['frame'] == frame), None)
    if selected is None:
        raise ValueError('The selected bone keyframe does not exist.')
    if new_frame != frame and any(k['frame'] == new_frame for k in keys):
        raise ValueError('A bone keyframe already exists at the destination.')
    selected['frame'] = new_frame
    return validate_layer(result)


def set_range(layer, bone, first, last, translation=(0, 0, 0), rotation=(0, 0, 0), space='local'):
    """Replace the inclusive interval and preserve the neighboring offsets."""
    result = validate_layer(layer)
    _integer(first, 'First frame')
    _integer(last, 'Last frame')
    if not first <= last < result['frames']:
        raise ValueError('Select a valid bone frame range.')
    track = result['tracks'].get(bone)
    if track and track['space'] != space:
        raise ValueError('Clear this bone track before changing its coordinate space.')
    keys = [key for key in track['keys'] if not first - 1 <= key['frame'] <= last + 1] if track else []
    for frame in (first - 1, last + 1):
        if 0 <= frame < result['frames']:
            transform = sample_offset(track, frame) if track else np.eye(4)
            keys.append(dict(frame=frame, translation=transform[:3, 3].tolist(),
                             rotation=_euler_xyz(transform[:3, :3])))
    for frame in sorted({first, last}):
        keys.append(dict(frame=frame, translation=list(translation), rotation=list(rotation)))
    result['tracks'][bone] = dict(space=space, keys=keys)
    return validate_layer(result)


def _euler_xyz(matrix):
    horizontal = np.hypot(matrix[0, 0], matrix[1, 0])
    y = np.arctan2(-matrix[2, 0], horizontal)
    if horizontal > 1e-8:
        x = np.arctan2(matrix[2, 1], matrix[2, 2])
        z = np.arctan2(matrix[1, 0], matrix[0, 0])
    else:
        x = np.arctan2(-matrix[1, 2], matrix[1, 1])
        z = 0.
    return np.degrees([x, y, z]).tolist()


def _quaternion(degrees):
    # xyzw quaternion; lowercase scipy xyz convention (extrinsic XYZ).
    x, y, z = np.radians(degrees) * .5
    sx, sy, sz = np.sin([x, y, z])
    cx, cy, cz = np.cos([x, y, z])
    return np.array([sx*cy*cz-cx*sy*sz, cx*sy*cz+sx*cy*sz,
                     cx*cy*sz-sx*sy*cz, cx*cy*cz+sx*sy*sz])


def _rotation(q):
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def sample_offset(track, frame):
    """Interpolate translation linearly and orientation along the shortest arc."""
    matrix = np.eye(4)
    if track is None or not track.get('keys'):
        return matrix
    keys = track['keys']
    frames = [key['frame'] for key in keys]
    right = int(np.searchsorted(frames, frame, side='right'))
    a = keys[max(0, right - 1)]
    b = keys[min(len(keys) - 1, right)]
    t = 0. if a['frame'] == b['frame'] else float(np.clip((frame-a['frame'])/(b['frame']-a['frame']), 0, 1))
    qa, qb = _quaternion(a['rotation']), _quaternion(b['rotation'])
    dot = float(qa @ qb)
    if dot < 0:
        qb = -qb
        dot = -dot
    dot = float(np.clip(dot, -1, 1))
    if dot > .9995:
        q = qa*(1-t) + qb*t
    else:
        angle = np.arccos(dot)
        q = (np.sin((1-t)*angle)*qa + np.sin(t*angle)*qb) / np.sin(angle)
    matrix[:3, :3] = _rotation(q)
    matrix[:3, 3] = np.asarray(a['translation'])*(1-t) + np.asarray(b['translation'])*t
    return matrix


def hierarchy_order(parents):
    parents = np.asarray(parents)
    if parents.ndim != 1 or len(parents) > MAX_BONES or parents.dtype.kind not in 'iu':
        raise ValueError('Invalid bone hierarchy.')
    n = len(parents)
    if np.any(parents < -1) or np.any(parents >= n):
        raise ValueError('Invalid bone parent index.')
    order, pending = [], set(range(n))
    while pending:
        ready = sorted(i for i in pending if parents[i] < 0 or int(parents[i]) not in pending)
        if not ready:
            raise ValueError('Bone hierarchy contains a cycle.')
        order.extend(ready)
        pending.difference_update(ready)
    return order


def _orientation(matrix):
    u, _, v = np.linalg.svd(matrix)
    out = u @ v
    if np.linalg.det(out) < 0:
        u[:, -1] *= -1
        out = u @ v
    return out


def apply_layer(palette, rest, parents, names, layer, frame):
    """Apply one sampled offset layer to immutable full-bone skin matrices."""
    names = list(map(str, names))
    n = len(names)
    order = hierarchy_order(parents)
    if len(set(names)) != n or len(parents) != n:
        raise ValueError('Invalid or duplicate skeleton bone names.')
    palette = np.asarray(palette)
    rest = np.asarray(rest)
    if palette.shape != (n + 1, 4, 4) or rest.shape != (n, 4, 4):
        raise ValueError('Bone edit preview requires the full skeleton palette.')
    if not np.isfinite(palette).all() or not np.isfinite(rest).all():
        raise ValueError('Bone matrices contain invalid values.')
    if layer is None or not layer['enabled'] or not layer['tracks']:
        return palette.copy()
    if not 0 <= frame < layer['frames']:
        raise ValueError('Bone frame is outside the animation.')
    unknown = set(layer['tracks']).difference(names)
    if unknown:
        raise ValueError('The skeleton does not contain bone: ' + sorted(unknown)[0])
    original = palette[:-1] @ rest
    edited = np.empty_like(original, dtype=np.float64)
    inverse = np.linalg.inv(original)
    for i in order:
        parent = int(parents[i])
        before = original[i].copy() if parent < 0 else edited[parent] @ inverse[parent] @ original[i]
        track = layer['tracks'].get(names[i])
        if track:
            delta = sample_offset(track, frame)
            if track['space'] == 'local':
                before[:3, 3] += _orientation(before[:3, :3]) @ delta[:3, 3]
                before[:3, :3] = before[:3, :3] @ delta[:3, :3]
            else:
                before[:3, :3] = delta[:3, :3] @ before[:3, :3]
                before[:3, 3] += delta[:3, 3]
        edited[i] = before
    result = np.empty_like(palette)
    result[:-1] = edited @ np.linalg.inv(rest)
    result[-1] = palette[-1]
    return result
