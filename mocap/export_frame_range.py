"""Frame metadata and bounds for exporting committed animation takes."""

import json
import math
from pathlib import Path


def source_frame_span(project, kind):
    """Return the start in source seconds, sample rate and committed frame count."""
    from .gemx_result import manifest

    project = Path(project)
    state = manifest(project)
    if state.get('pipeline', {}).get('model') == 'gemx':
        result = state
    else:
        result = json.loads((project / f'{kind}_mixamo.json').read_text(encoding='utf-8'))
    start = float(state.get('start', 0.0))
    fps = float(result['fps'])
    frames = result['frames']
    if not math.isfinite(start) or not math.isfinite(fps) or fps <= 0 or type(frames) is not int or frames < 1:
        raise ValueError('Invalid committed animation timing.')
    return start, fps, frames


def checked_frame_slice(value, frames):
    """Validate half-open, take-local sample bounds before reading animation."""
    if value is None:
        return slice(None)
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(type(index) is not int for index in value):
        raise ValueError('Invalid FBX frame slice.')
    start, stop = value
    if not 0 <= start < stop <= frames:
        raise ValueError('The export range is outside the committed animation take. Select the range again.')
    return slice(start, stop)
