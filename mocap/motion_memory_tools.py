"""Analyze a selected take and save reviewed examples for later AI sessions."""
from pathlib import Path

import numpy as np

from . import motion_memory as memory


def workspace_root(window):
    folder = window.workspace_root or window.character_root or window.project
    if folder is None or not (Path(folder) / 'project.json').is_file():
        raise ValueError('Open a saved RGB MoCap project first.')
    return Path(folder).resolve()


def analyze(controller, frame_start, frame_end):
    """Sample the displayed take using the same evaluator as bone preview."""
    if (type(frame_start) is not int or type(frame_end) is not int or
            not 0 < frame_start <= frame_end or frame_end - frame_start + 1 > memory.MAX_FRAMES):
        raise ValueError(f'Select an inclusive range of 1–{memory.MAX_FRAMES} frames.')
    if controller.source_mode:
        source = controller._source_context()
        if frame_end > source.frames:
            raise ValueError('The range is outside this source take.')
        points = np.stack([source.geometry(frame)['heads'] for frame in range(frame_start - 1, frame_end)])
        summary = memory.summarize_motion(points, source.names, source.fps, parents=source.parents)
        return dict(summary=summary, source_kind='captured')

    if controller._context(required=False) is None:
        controller.prepare(wait=True)
    context = controller._context()
    if frame_end > context['frames']:
        raise ValueError('The range is outside this character take.')

    from .bone_animation import apply_layer
    skeleton = context['skeleton']
    heads = skeleton['rest'][:, :, 3]
    names, parents = context['names'], skeleton['parents']
    take, layer = context['take'], context['layer']
    placement = np.asarray(take.get('transform') if take.get('transform') is not None else np.eye(4))
    points, baseline = [], []
    use_edits = bool(layer['enabled'] and layer['tracks'])
    for frame in range(frame_start - 1, frame_end):
        palette = context['array'][frame]
        base = (palette[:-1] @ heads[..., None])[:, :3, 0]
        baseline.append(base @ placement[:3, :3].T + placement[:3, 3])
        if use_edits:
            edited = apply_layer(palette, skeleton['rest'], parents, names, layer, frame)
            positions = (edited[:-1] @ heads[..., None])[:, :3, 0]
            points.append(positions @ placement[:3, :3].T + placement[:3, 3])
    original = memory.summarize_motion(np.asarray(baseline), names, take['fps'], parents=parents)
    if not use_edits:
        return dict(summary=original, source_kind='retargeted')
    return dict(summary=memory.summarize_motion(np.asarray(points), names, take['fps'], parents=parents),
                reference_summary=original, source_kind='edited')


def remember(controller, *, frame_start, frame_end, label, note=''):
    root = workspace_root(controller.window)
    target = next((c for c in controller._targets() if c['id'] == controller.character_id), None)
    if target is None:
        raise ValueError('Select a source person or a retargeted character.')
    result = analyze(controller, frame_start, frame_end)
    return memory.save_example(root, label=label, note=note, subject=target['name'],
                               frame_start=frame_start, frame_end=frame_end, summary=result['summary'],
                               reference_summary=result.get('reference_summary'))


def search(window, query='', limit=10, include_other_projects=False):
    from .paths import PROJECTS
    root = workspace_root(window)
    rows = [dict(row, project_name=root.name, current_project=True)
            for row in memory.search_examples(root, query, limit=limit)]
    if not include_other_projects or len(rows) >= limit or not PROJECTS.is_dir():
        return rows

    libraries = []
    library_root = PROJECTS.resolve()
    for directory in library_root.iterdir():
        try:
            if directory == root or directory.resolve().parent != library_root or directory.is_symlink() or not directory.is_dir():
                continue
            path = directory / memory.FILENAME
            if path.is_file() and not path.is_symlink():
                libraries.append((path.stat().st_mtime_ns, directory))
        except OSError:
            continue
    seen = {row['id'] for row in rows}
    for _, folder in sorted(libraries, reverse=True)[:32]:
        try:
            results = memory.search_examples(folder, query, limit=limit)
        except (OSError, ValueError):
            continue
        for row in results:
            if row['id'] not in seen:
                seen.add(row['id'])
                rows.append(dict(row, project_name=folder.name, current_project=False))
                if len(rows) >= limit:
                    return rows
    return rows
