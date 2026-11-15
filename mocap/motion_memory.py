"""Project-local summaries of explicitly approved motion examples."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import stat
from threading import RLock
import unicodedata
import uuid

import numpy as np

from .bone_animation import hierarchy_order
from .storage import atomic_json

FILENAME = 'motion-memory.json'
MAX_FRAMES = 600
MAX_BONES = 4096
MAX_EXAMPLES = 250
MAX_JOINTS = 12
MAX_BYTES = 4 * 1024 * 1024
_BONE_NAME_LIMIT = 512
_VERSION = 1
_LOCK = RLock()
_ID = re.compile(r'[0-9a-f]{32}\Z')


def _text(value, field, limit, *, required=False):
    if not isinstance(value, str):
        raise ValueError(f'{field} must be text.')
    value = value.strip()
    if len(value) > limit or (required and not value):
        raise ValueError(f'{field} must contain {"1 to " if required else "at most "}{limit} characters.')
    if any(unicodedata.category(c) == 'Cs' or (ord(c) < 32 and c not in '\r\n\t') for c in value):
        raise ValueError(f'{field} contains an invalid character.')
    return value


def _integer(value, field, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f'{field} must be an integer between {lower} and {upper}.')
    return value


def _number(value, field, lower=0., upper=1e9):
    if (isinstance(value, (bool, np.bool_)) or
            not isinstance(value, (int, float, np.integer, np.floating)) or
            not lower <= value <= upper):
        raise ValueError(f'{field} is outside its valid bounds.')
    return float(value)


def summarize_motion(positions, names, fps, *, parents=None):
    """Describe sampled joint centres in metres and seconds.

    Parent-relative paths subtract the parent's position in the same world axes.
    A bend is the angle at a joint toward its parent and longest child.
    """
    points = np.asarray(positions)
    if points.ndim != 3 or points.shape[-1] != 3 or points.dtype.kind not in 'fiu':
        raise ValueError('Joint positions must be a numeric array shaped [frames, bones, 3].')
    frames, bones, _ = points.shape
    _integer(frames, 'Frame count', 1, MAX_FRAMES)
    _integer(bones, 'Bone count', 1, MAX_BONES)
    fps = _number(fps, 'Frame rate', .01, 1000.)
    names = [_text(name, 'Bone name', _BONE_NAME_LIMIT, required=True) for name in names]
    if len(names) != bones or len(set(names)) != bones:
        raise ValueError('Provide one unique name for each bone.')
    if parents is not None:
        parents = np.asarray(parents)
        if parents.shape != (bones,):
            raise ValueError('Provide one parent index for each bone.')
        hierarchy_order(parents)
        parents = parents.astype(np.intp, copy=False)

    # Keep work bounded for dense rigs. Include both ends and use actual
    # sample intervals when computing speeds.
    count = min(frames, max(2, 160000 // bones))
    indices = np.linspace(0, frames - 1, count).round().astype(np.intp)
    sampled = points[indices].astype(np.float64, copy=False)
    if not np.isfinite(sampled).all() or np.max(np.abs(sampled)) > 1e5:
        raise ValueError('Joint positions contain invalid metre values.')
    relative = sampled.copy()
    children = {}
    if parents is not None:
        for index, parent in enumerate(parents):
            if parent >= 0:
                relative[:, index] -= sampled[:, parent]
                children.setdefault(parent, []).append(index)

    world_steps = np.linalg.norm(np.diff(sampled, axis=0), axis=2)
    relative_steps = np.linalg.norm(np.diff(relative, axis=0), axis=2)
    world_path = world_steps.sum(axis=0)
    relative_path = relative_steps.sum(axis=0)
    speed = (np.percentile(relative_steps / (np.diff(indices) / fps)[:, None], 90, axis=0)
             if count > 1 else np.zeros(bones))
    span = np.ptp(sampled, axis=0)
    order = sorted(range(bones), key=lambda i: (-relative_path[i], -world_path[i], names[i]))
    records = []
    for index in order[:MAX_JOINTS]:
        joint = dict(name=names[index], world_path_m=round(float(world_path[index]), 6),
                     relative_path_m=round(float(relative_path[index]), 6),
                     relative_speed_p90_m_s=round(float(speed[index]), 6),
                     world_range_xyz_m=np.round(span[index], 6).tolist())
        if parents is not None and parents[index] >= 0:
            joint['parent'] = names[parents[index]]
            if index in children:
                to_parent = -relative[:, index]
                child = max(children[index], key=lambda i: np.median(np.linalg.norm(relative[:, i], axis=1)))
                to_child = relative[:, child]
                scale = np.linalg.norm(to_parent, axis=1) * np.linalg.norm(to_child, axis=1)
                valid = scale > 1e-12
                if valid.any():
                    cosine = np.sum(to_parent[valid] * to_child[valid], axis=1) / scale[valid]
                    angles = np.degrees(np.arccos(np.clip(cosine, -1., 1.)))
                    joint['angle_child'] = names[child]
                    joint['bend_range_deg'] = np.round([angles.min(), angles.max()], 3).tolist()
        records.append(joint)
    return dict(frames=frames, samples=count, bones=bones, fps=fps,
                duration_seconds=round((frames - 1) / fps, 6),
                parent_relative=parents is not None, joints=records)


def _normalize_summary(summary):
    """Allow only compact metrics into the persisted library."""
    if not isinstance(summary, dict):
        raise ValueError('Provide a motion summary.')
    try:
        frames = _integer(summary['frames'], 'Frame count', 1, MAX_FRAMES)
        samples = _integer(summary['samples'], 'Sample count', 1, frames)
        bones = _integer(summary['bones'], 'Bone count', 1, MAX_BONES)
        fps = _number(summary['fps'], 'Frame rate', .01, 1000.)
        relative = summary['parent_relative']
        joints = summary['joints']
        if type(relative) is not bool or not isinstance(joints, list) or not 1 <= len(joints) <= min(bones, MAX_JOINTS):
            raise ValueError('Invalid motion summary.')
        records = []
        for joint in joints:
            fields = ('world_path_m', 'relative_path_m', 'relative_speed_p90_m_s')
            record = {'name': _text(joint['name'], 'Bone name', _BONE_NAME_LIMIT, required=True)}
            record.update({field: _number(joint[field], field) for field in fields})
            span = joint['world_range_xyz_m']
            if not isinstance(span, list) or len(span) != 3:
                raise ValueError('Invalid joint range.')
            record['world_range_xyz_m'] = [_number(value, 'Joint range') for value in span]
            if 'parent' in joint:
                record['parent'] = _text(joint['parent'], 'Parent bone', _BONE_NAME_LIMIT, required=True)
            if 'bend_range_deg' in joint:
                bend = joint['bend_range_deg']
                if not isinstance(bend, list) or len(bend) != 2:
                    raise ValueError('Invalid bend range.')
                low, high = [_number(value, 'Bend angle', 0., 180.) for value in bend]
                if high < low:
                    raise ValueError('Invalid bend range.')
                record['bend_range_deg'] = [low, high]
                record['angle_child'] = _text(joint['angle_child'], 'Child bone', _BONE_NAME_LIMIT, required=True)
            records.append(record)
        if len({j['name'] for j in records}) != len(records):
            raise ValueError('Motion summary contains duplicate bones.')
        return dict(frames=frames, samples=samples, bones=bones, fps=fps, parent_relative=relative,
                    duration_seconds=round((frames - 1) / fps, 6), joints=records)
    except (KeyError, TypeError) as exc:
        raise ValueError('Invalid motion summary.') from exc


def _is_regular(path):
    stamp = path.lstat()
    return stat.S_ISREG(stamp.st_mode) and not getattr(stamp, 'st_file_attributes', 0) & 0x400


def _path(workspace):
    root = Path(workspace).resolve(strict=True)
    marker = root / 'project.json'
    if not marker.is_file() or not _is_regular(marker):
        raise ValueError('Open a saved RGB MoCap project before using Motion Memory.')
    path = root / FILENAME
    if (path.exists() or path.is_symlink()) and not _is_regular(path):
        raise ValueError('Motion Memory must be a regular file in this project.')
    return path


def _read(path):
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return []
    if len(raw) > MAX_BYTES:
        raise ValueError('Motion Memory exceeds the project size limit.')
    try:
        value = json.loads(raw)
        examples = value['examples']
        if (type(value['version']) is not int or value['version'] != _VERSION or
                not isinstance(examples, list) or len(examples) > MAX_EXAMPLES or
                any(not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or
                    not _ID.fullmatch(entry['id']) for entry in examples) or
                len({entry['id'] for entry in examples}) != len(examples)):
            raise ValueError
        return [_normalize_example(entry) for entry in examples]
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise ValueError('Motion Memory file is damaged or unsupported.') from exc


def _write(path, examples):
    document = dict(version=_VERSION, examples=examples)
    if len(json.dumps(document, ensure_ascii=False, indent=2).encode('utf-8')) > MAX_BYTES:
        raise ValueError('Motion Memory is full. Remove an example before adding another.')
    atomic_json(path, document)


def _normalize_example(entry):
    first = _integer(entry['frame_start'], 'First frame', 1, 2147483647)
    last = _integer(entry['frame_end'], 'Last frame', first, min(2147483647, first + MAX_FRAMES - 1))
    summary = _normalize_summary(entry['summary'])
    if summary['frames'] != last - first + 1:
        raise ValueError('Motion summary does not match the selected frame range.')
    saved = _text(entry['saved_utc'], 'Saved timestamp', 40, required=True)
    if datetime.fromisoformat(saved).utcoffset() is None:
        raise ValueError('Saved timestamp must include the time zone.')
    row = dict(id=entry['id'], label=_text(entry['label'], 'Example label', 120, required=True),
               note=_text(entry['note'], 'Example note', 1200), subject=_text(entry['subject'], 'Subject', 255),
               frame_start=first, frame_end=last, summary=summary,
               saved_utc=saved)
    reference_summary = entry.get('reference_summary')
    if reference_summary is not None:
        reference = _normalize_summary(reference_summary)
        if (reference['frames'], reference['fps'], reference['bones']) != (summary['frames'], summary['fps'], summary['bones']):
            raise ValueError('Reference and example must describe the same skeleton size, frame range and rate.')
        row['reference_summary'] = reference
    return row


def save_example(workspace, *, label, summary, frame_start, frame_end, note='', subject='', reference_summary=None):
    """Save a user-approved example. Frame numbers are one-based and inclusive."""
    row = _normalize_example(dict(id=uuid.uuid4().hex, label=label, note=note, subject=subject,
                                  summary=summary, reference_summary=reference_summary,
                                  frame_start=frame_start, frame_end=frame_end,
                                  saved_utc=datetime.now(timezone.utc).isoformat(timespec='seconds')))
    with _LOCK:
        path = _path(workspace)
        examples = _read(path)
        if len(examples) >= MAX_EXAMPLES:
            raise ValueError('Motion Memory is full. Remove an example before adding another.')
        _write(path, [*examples, row])
    return row


def _normalize_query(text):
    return ' '.join(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', text).casefold()))


def search_examples(workspace, query='', *, limit=10):
    """Find approved examples by label, subject, note or joint name."""
    query = _normalize_query(_text(query, 'Search query', 250))
    limit = _integer(limit, 'Search limit', 1, 50)
    entries = _read(_path(workspace))
    if not query:
        return entries[::-1][:limit]
    if _ID.fullmatch(query):
        return [row for row in entries if row['id'] == query]
    ranked = []
    terms = query.split()
    for index, row in enumerate(entries):
        joints = row.get('summary', {}).get('joints', [])
        fields = [(row.get('label', ''), 4), (row.get('subject', ''), 2), (row.get('note', ''), 2)]
        fields.extend((j.get('name', ''), 1) for j in joints)
        values = [(_normalize_query(value), weight) for value, weight in fields]
        scores = [max((weight for value, weight in values if term in value), default=0) for term in terms]
        if all(scores):
            phrase = max((weight for value, weight in values if query in value), default=0)
            ranked.append((sum(scores) + phrase, index, row))
    ranked.sort(reverse=True, key=lambda item: item[:2])
    return [row for _, _, row in ranked[:limit]]


def delete_example(workspace, example_id):
    """Remove precisely one existing example by its stable identifier."""
    if not isinstance(example_id, str) or not _ID.fullmatch(example_id):
        raise ValueError('Provide a Motion Memory example ID.')
    with _LOCK:
        path = _path(workspace)
        entries = _read(path)
        remaining = [row for row in entries if row['id'] != example_id]
        if len(remaining) == len(entries):
            return False
        _write(path, remaining)
        return True
