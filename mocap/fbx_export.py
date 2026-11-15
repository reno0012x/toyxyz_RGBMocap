"""Cancellable, transactional FBX export of the selected committed generation."""
import json
import os
from pathlib import Path
import numpy as np
from .motion_tools import selected_export
from .result_artifacts import file_stat
from .export_frame_range import checked_frame_slice


def _publish(temporary, target, no_overwrite):
    if not no_overwrite:
        os.replace(temporary, target)
    elif os.name == 'nt':
        os.rename(temporary, target)  # Windows rename never replaces an existing path.
    else:
        os.link(temporary, target)


def run(request, emit=lambda *a, **k:None):
    from .blend_support import build, cleanup, partial
    from .fbx_writer import write
    from .gemx_result import is_project
    from .scene_export import context
    request=Path(request)
    if request.stat().st_size>4*1024**2:raise ValueError('Export request is too large')
    rows=json.loads(request.read_text(encoding='utf-8'))
    if not isinstance(rows,list) or not 1<=len(rows)<=4096:raise ValueError('Invalid export request')
    staged=[];origins={};committed=[];native_checks=[]
    compatibility_dirs=[]
    try:
        destinations = {Path(row['target']).resolve() for row in rows}
        if len(destinations) != len(rows):raise ValueError('Duplicate export destination')
        for i,row in enumerate(rows):
            project=Path(row['project']);kind=row['kind'];target=Path(row['target'])
            source=selected_export(project,kind)
            if source is None or source.resolve()!=Path(row['source']).resolve():
                raise ValueError('Selected target motion changed. Prepare Preview and export again.')
            if target.suffix.lower()!='.fbx':raise ValueError('Choose an FBX destination')
            no_overwrite = row.get('no_overwrite', False)
            if no_overwrite and os.path.lexists(target):
                raise FileExistsError(f'Export destination already exists: {target}')
            temporary=partial(target,request)
            output=temporary
            work=None
            if row.get('fbx_compatibility',False):
                work=temporary
                work.mkdir()
                owner=work/'.rgbmocap-owner'
                try:
                    owner.write_text(request.stem,encoding='utf-8')
                except OSError:
                    owner.unlink(missing_ok=True)
                    work.rmdir()
                    raise
                compatibility_dirs.append(work)
                temporary=work/'source.fbx'
                output=work/'compatible.fbx'
            if is_project(project):
                from .gemx_skeleton_export import write as write_soma

                def progress(done,total):
                    emit('progress',stage='save_fbx',current=i*total+done,total=len(rows)*total,message='Export SOMA FBX')

                staged.append((output,target,work,no_overwrite))
                native_checks.append(write_soma(temporary,row,source,destinations,'fbx',progress))
                continue
            meta=project/(kind+'_mixamo.json');info=json.loads(meta.read_text(encoding='utf-8'))
            paths=[meta,source]
            for key in ('asset_file','frames_file'):
                if Path(info[key]).name!=info[key]:raise ValueError('Invalid committed file path')
                paths.append(project/info[key])
            if destinations.intersection(p.resolve() for p in paths):raise ValueError('An export destination overlaps a committed source file.')
            stamps=[file_stat(p) for p in paths]
            scene=row.get('scene')
            if scene is not None and context(scene['root'],project)!=scene:raise ValueError('Scene placement changed. Export again.')
            staged.append((output,target,work,no_overwrite))
            committed.append((project,kind,paths,stamps,scene))
            with np.load(project/info['asset_file'],allow_pickle=False) as data:
                needed=('parents','fbx_rest','fbx_rest_frames','fbx_display_frames','fbx_tip_local')
                if not all(k in data for k in needed):raise ValueError('FBX rest pose is unavailable. Use Prepare Preview first.')
                a={k:data[k] for k in needed}
                symmetric=None
                if row.get('symmetric_rest',False):
                    if not all(k in data for k in ('rest','ends')):raise ValueError('Symmetric rest data is unavailable. Use Prepare Preview first.')
                    symmetric=dict(rest=data['rest'],ends=data['ends'])
            frame_data=np.load(project/info['frames_file'],mmap_mode='r',allow_pickle=False)
            try:
                frames = frame_data[checked_frame_slice(row.get('frame_slice'), len(frame_data))]
                transform=np.eye(4) if scene is None else np.asarray(scene['transform'],float)
                if row.get('place_at_origin',False):
                    from .export_options import centered_transform
                    transform=centered_transform(transform,frames[0,0,:3,3],origins,row.get('origin_group',str(project)))
                def progress(done,total):
                    emit('progress',stage='save_fbx',current=i*52+done,total=len(rows)*52,message='Export FBX: '+kind)
                write(temporary,info['names'],a['parents'],a['fbx_rest'],a['fbx_rest_frames'],
                      a['fbx_display_frames'],a['fbx_tip_local'],frames,info['fps'],
                      transform=transform,progress=progress,
                      rig_name=row.get('rig_name','SourceAnimation'),prepend_tpose=row.get('prepend_tpose',False),symmetric_bind=symmetric)
            finally:frame_data._mmap.close()
        for work in compatibility_dirs:
            build(work,'fbx_compatibility_scene.py',emit,'save_fbx')
            if not (work/'compatible.fbx').is_file():
                raise RuntimeError('Blender did not create the compatible FBX.')
            (work/'source.fbx').unlink()
        for verify in native_checks:verify()
        for project,kind,paths,stamps,scene in committed:
            if [file_stat(p) for p in paths]!=stamps or selected_export(project,kind)!=paths[1]:
                raise ValueError('Motion generation changed during export. Retry.')
            if scene is not None and context(scene['root'],project)!=scene:raise ValueError('Scene placement changed during export. Retry.')
        for temporary,target,_,no_overwrite in staged:_publish(temporary,target,no_overwrite)
        return len(staged)
    finally:
        for output,_,work,_ in staged:
            if work is None:output.unlink(missing_ok=True)
        for work in compatibility_dirs:cleanup(work,request)
        request.unlink(missing_ok=True)
