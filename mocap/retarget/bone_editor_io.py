"""Blender-only full skeleton preparation and non-destructive edit baking."""
from pathlib import Path
import json
import shutil
import tempfile

import bpy
import numpy as np
from mathutils import Matrix

from mocap.bone_animation import (apply_layer, base_identity_for, hierarchy_order,
                                  load_export_layer, validate_layer)
from .file_paths import io_path
from .mapping import A


def _axes():
    matrix = np.eye(4)
    matrix[:3, :3] = A.T
    return matrix


def skeleton(arm):
    names = sorted(b.name for b in arm.data.bones)
    lookup = {name: i for i, name in enumerate(names)}
    parents = np.array([lookup[arm.data.bones[name].parent.name]
                        if arm.data.bones[name].parent else -1 for name in names], dtype=np.int32)
    C = _axes()
    rest = np.array([C @ np.asarray(arm.matrix_world @ arm.data.bones[name].matrix_local) @ C.T
                     for name in names], dtype=np.float64)
    tails = np.array([arm.matrix_world @ arm.data.bones[name].tail_local for name in names]) @ A
    return names, parents, rest, tails


def prepare(out, base):
    """Create a separate full-bone cache, preserving the original animation."""
    from .blender_io import preview, report
    out, base = Path(out), Path(base)
    identity = base_identity_for(base)
    info = json.loads(Path(io_path(base / 'bake.json')).read_text(encoding='utf-8'))
    frames = info['frames']
    if type(frames) is not int or frames < 1:
        raise ValueError('Invalid baked character duration.')
    bpy.ops.wm.open_mainfile(filepath=io_path(base / 'animation.blend'), load_ui=False)
    arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    if len(arms) != 1:
        raise ValueError('Bone editing requires one character armature.')
    arm = arms[0]
    names, parents, rest, tails = skeleton(arm)
    if not 0 < len(names) <= 4096:
        raise ValueError('Bone editor supports 1 to 4096 bones.')
    hierarchy_order(parents)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(io_path(base / 'import.json'), io_path(out / 'import.json'))
    report('Preparing full bone hierarchy')
    np.savez(io_path(out / 'bone-skeleton.npz'), names=np.array(names), parents=parents,
             rest=rest, tails=tails)
    # preview(None) retains every bone's original skin weights and own palette.
    preview(out, arm, None, frames)
    if base_identity_for(base) != identity:
        raise ValueError('Character animation changed while preparing its bone editor.')
    scene = bpy.context.scene
    result = dict(version=1, frames=frames, fps=scene.render.fps / scene.render.fps_base,
                  base_identity=identity, bones=len(names),
                  skeleton_file='bone-skeleton.npz', frames_file='preview-frames.npy')
    Path(io_path(out / 'bone-editor.json')).write_text(json.dumps(result), encoding='utf-8')
    return result


def bake_edits(arm, folder, supplied=None):
    """Bake shared layer math in memory; the source .blend remains untouched."""
    from .blender_bake import key_values
    from .blender_io import report
    folder = Path(folder)
    info = json.loads(Path(io_path(folder / 'bake.json')).read_text(encoding='utf-8'))
    layer = supplied if supplied is not None else load_export_layer(folder)
    if layer is None:
        return set()
    names, parents, rest, _ = skeleton(arm)
    layer = validate_layer(layer, names=names, frames=info['frames'],
                           base_identity=base_identity_for(folder))
    if not layer['enabled'] or not layer['tracks']:
        return set()
    count, total = len(names), info['frames']
    order = hierarchy_order(parents)
    inverse_rest = np.linalg.inv(rest)
    C = _axes()
    arm_world = np.asarray(arm.matrix_world, dtype=np.float64)
    inverse_arm = np.linalg.inv(arm_world)
    scene = bpy.context.scene
    report('Baking bone edit layer for export')
    # Disk-backed arrays bound RAM independently of animation length.
    with tempfile.TemporaryDirectory(prefix='rgbmocap-bone-bake-') as scratch:
        raw = np.lib.format.open_memmap(str(Path(scratch) / 'poses.npy'), mode='w+',
                                        dtype=np.float64, shape=(total, count + 1, 4, 4))
        channels = np.lib.format.open_memmap(str(Path(scratch) / 'channels.npy'), mode='w+',
                                             dtype=np.float64, shape=(total, count, 10))
        try:
            for frame in range(total):
                scene.frame_set(frame + 1)
                bpy.context.view_layer.update()
                posed = np.array([C @ np.asarray(arm.matrix_world @ arm.pose.bones[name].matrix) @ C.T
                                  for name in names])
                raw[frame, :-1] = posed @ inverse_rest
                raw[frame, -1] = np.eye(4)
            # Every original evaluated helper is retained by baking its local
            # channels, rather than keeping a constraint dependent on old keys.
            arm.animation_data_clear()
            for bone in arm.pose.bones:
                for constraint in bone.constraints:
                    constraint.mute = True
            previous = None
            for frame in range(total):
                edited = apply_layer(raw[frame], rest, parents, names, layer, frame)
                posed = edited[:-1] @ rest
                matrices = [Matrix((inverse_arm @ C.T @ value @ C).tolist()) for value in posed]
                for i in order:
                    bone = arm.data.bones[names[i]]
                    options = {}
                    if parents[i] >= 0:
                        options = dict(parent_matrix=matrices[int(parents[i])],
                                       parent_matrix_local=bone.parent.matrix_local)
                    basis = bone.convert_local_to_pose(matrices[i], bone.matrix_local, invert=True, **options)
                    location, quaternion, scale = basis.decompose()
                    values = np.r_[tuple(location), tuple(quaternion), tuple(scale)]
                    if previous is not None and values[3:7] @ previous[i, 3:7] < 0:
                        values[3:7] *= -1
                    channels[frame, i] = values
                previous = channels[frame].copy()
            for i, name in enumerate(names):
                bone = arm.pose.bones[name]
                bone.rotation_mode = 'QUATERNION'
                for path, section in (('location', slice(0, 3)), ('rotation_quaternion', slice(3, 7)),
                                      ('scale', slice(7, 10))):
                    values = np.asarray(channels[:, i, section])
                    setattr(bone, path, values[0])
                    bone.keyframe_insert(path, frame=1)
                    key_values(arm, bone.path_from_id(path), values)
            scene.frame_start = 1
            scene.frame_end = total
            scene.frame_set(1)
        finally:
            raw.flush()
            channels.flush()
            raw._mmap.close()
            channels._mmap.close()
    return set(names)
