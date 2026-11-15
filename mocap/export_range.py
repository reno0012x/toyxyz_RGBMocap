"""Translate one-based workspace frame selections to saved motion samples."""

import math


def frame_slice(frame_start, frame_end, *, timeline_start, timeline_fps,
                take_start, take_fps, take_frames):
    """Return an intersecting zero-based, half-open slice, or None."""
    if type(frame_start) is not int or type(frame_end) is not int or not 1 <= frame_start <= frame_end:
        raise ValueError('Select a valid start and end frame.')
    if not (timeline_fps > 0 and take_fps > 0 and take_frames > 0):
        raise ValueError('The saved motion has an invalid frame rate or length.')

    def displayed_sample(frame):
        time_from_take = timeline_start - take_start + frame / timeline_fps
        return math.floor(time_from_take * take_fps + 1e-6)

    first = max(0, displayed_sample(frame_start - 1))
    stop = min(take_frames, displayed_sample(frame_end - 1) + 1)
    return (first, stop) if first < stop else None


def source_slice(window, project, kind, frame_start, frame_end):
    from .export_frame_range import source_frame_span

    start, fps, frames = source_frame_span(project, kind)
    return frame_slice(
        frame_start, frame_end, timeline_start=window.source_offset,
        timeline_fps=float(window.info['fps']), take_start=start,
        take_fps=fps, take_frames=frames,
    )


def export_saved_fbx(window, destination, frame_start=None, frame_end=None):
    """Run the regular source FBX exporter without writing a project job file."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from .export_frame_range import source_frame_span
    from .fbx_export import run
    from .scene_export import context
    from .storage import atomic_json

    source = window.current_export()
    if source is None or window.project is None:
        raise ValueError('The selected person has no saved exportable motion.')
    project, kind = window.project, window.active_result
    _, fps, frame_count = source_frame_span(project, kind)
    row = {'project': str(project), 'kind': kind, 'source': str(source),
           'target': str(destination), 'rig_name': window.export_person_name(project),
           'no_overwrite': True}
    if frame_start is not None:
        selected = source_slice(window, project, kind, frame_start, frame_end)
        if selected is None:
            raise ValueError('The selected frames do not overlap this take.')
        row['frame_slice'] = selected
        frame_count = selected[1] - selected[0]
    if window.people_root is not None:
        row['scene'] = context(window.people_root, project)
    with TemporaryDirectory(prefix='rgbmocap-fbx-') as scratch:
        request = Path(scratch) / (Path(scratch).name + '.json')
        atomic_json(request, [row])
        run(request)
    return {'output_path': str(destination), 'frames': frame_count, 'fps': fps,
            'frame_start': frame_start, 'frame_end': frame_end, 'result': kind,
            'project': str(project)}
