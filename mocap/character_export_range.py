"""Use existing baked character motion for FBX range and MCP exports."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from .export_range import frame_slice


def character_export_takes(character, frame_start=None, frame_end=None, *,
                           timeline_start=None, timeline_fps=None):
    """Return original take numbers and optional native frame slices."""
    numbered = list(enumerate(character['takes'], 1))
    if frame_start is None and frame_end is None:
        return numbered

    overlapping = []
    for number, take in numbered:
        section = frame_slice(
            frame_start, frame_end, timeline_start=timeline_start,
            timeline_fps=timeline_fps, take_start=take['start'],
            take_fps=take['fps'], take_frames=take['frames'],
        )
        if section is not None:
            overlapping.append((number, dict(take, frame_slice=section)))
    return overlapping


def export_saved_character_fbx(window, destination, character_name=None,
                               frame_start=None, frame_end=None, *, character_id=None):
    """Export one baked take and publish its file without replacing an existing file."""
    from .retarget.worker import invoke

    if character_id is not None:
        matches = [character for character in window.characters if character['id'] == character_id]
    elif character_name:
        matches = [character for character in window.characters
                   if character['name'].casefold() == character_name.casefold()]
    else:
        raise ValueError('Select a character by name or ID.')
    if not matches:
        raise ValueError('No imported character matches that selection.')
    if len(matches) > 1:
        raise ValueError('Several imported characters share that name. Use character_id from get_status.')
    character = matches[0]
    if character.get('needs_retarget'):
        raise ValueError('Character motion is out of date. Apply Correction or retarget it again.')
    if not character.get('animation') or not character.get('takes'):
        raise ValueError('The character has no saved exportable motion.')

    takes = character_export_takes(
        character, frame_start, frame_end, timeline_start=window.source_offset,
        timeline_fps=float(window.info['fps']),
    )
    if not takes:
        raise ValueError('The selected frames do not contain character motion.')
    if len(takes) > 1:
        raise ValueError('Several character takes match. Select a frame range within one take.')
    _, take = takes[0]
    folder = window.character_path(character['animation'] + '/' + take['folder'])
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError('The export file already exists.')

    options = dict(format='fbx', include_mesh=True)
    if 'frame_slice' in take:
        options['frame_slice'] = take['frame_slice']
    first, stop = options.get('frame_slice', (0, take['frames']))
    with TemporaryDirectory(prefix='rgbmocap-character-fbx-') as scratch:
        with NamedTemporaryFile(prefix='.rgbmocap-fbx-', suffix='.fbx',
                                dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            invoke('export', Path(scratch), folder, temporary, json.dumps(take.get('transform')),
                   character['name'], json.dumps(options))
            if not temporary.stat().st_size:
                raise RuntimeError('Character FBX export did not produce a file.')
            if os.name == 'nt':
                # Windows rename fails atomically if the name already exists.
                temporary.rename(target)
            else:
                os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    return {'output_path': str(target), 'frames': stop - first, 'fps': take['fps'],
            'frame_start': frame_start, 'frame_end': frame_end,
            'character_name': character['name'], 'project': str(window.workspace_root or window.project)}
