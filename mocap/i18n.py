"""Offline UI translations. Display text only; model/project identities stay intact."""
from __future__ import annotations
import json
import re
from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QAbstractButton, QComboBox, QGroupBox,
                              QLabel, QTabBar, QTableWidget, QTextBrowser, QWidget)

TH = {
    'Motion target':'เลือกบุคคลหรือตัวละคร',
    'Choose a source person or retargeted character.':'เลือกบุคคลต้นทางหรือตัวละครที่ถ่ายท่าแล้ว',
    'Source motion · view only':'ต้นทาง · ดูโครงกระดูก',
    'Prepare the source motion preview first.':'กดเตรียมภาพตัวอย่างเพื่อโหลดโครงกระดูกต้นทาง',
    'Check this character in People to show it in the viewport.':'ติ๊กตัวละครนี้ในรายการบุคคลเพื่อแสดงในมุมมอง 3D',
    'Open Bone Editor in a separate window':'เปิดหน้าต่างแก้ไขกระดูกแยก',
    'Dock Bone Editor':'คืนแท็บแก้ไขกระดูก',
    'Drag this tab out to open a separate window':'ลากแท็บออกเพื่อเปิดเป็นหน้าต่างแยก',
    'Bone Editor is open in a separate window.':'เปิดตัวแก้กระดูกในหน้าต่างแยกอยู่',
    'Bone Editor':'แก้ไขกระดูก', 'Prepare Bone Editor':'เตรียมแก้ไขกระดูก',
    'Preparing Bone Editor...':'กำลังเตรียมกระดูก...',
    'Enable edit layer':'เปิดชั้นแก้ไข', 'Save edits':'บันทึกการแก้ไข',
    'Undo':'ย้อนกลับ', 'Redo':'ทำซ้ำ', 'Search bones':'ค้นหากระดูก',
    'No bone selected':'ยังไม่ได้เลือกกระดูก', 'Select a bone to edit.':'เลือกกระดูกที่ต้องการแก้ไข',
    'Prepare the Bone Editor to edit this take.':'กดเตรียมแก้ไขกระดูกเพื่อเริ่มงาน',
    'Select a retargeted character, then prepare its bones.':'เลือกตัวละครที่ถ่ายท่าแล้ว จากนั้นกดเตรียมแก้ไขกระดูก',
    'Choose the character to edit.':'เลือกตัวละครที่ต้องการแก้ไข',
    'Select':'เลือก', 'Move':'ย้าย', 'Rotate':'หมุน', 'Local':'แกนกระดูก', 'World':'แกนฉาก',
    'Position offset (m)':'ระยะย้าย (ม.)', 'Rotation offset (°)':'มุมหมุน (°)',
    'Auto Key':'คีย์อัตโนมัติ', 'Reset offset':'คืนค่าการปรับ',
    'Add / Update Key':'เพิ่ม / อัปเดตคีย์', 'Delete Key':'ลบคีย์',
    'Apply to range':'ใช้กับช่วง', 'Clear bone track':'ล้างคีย์กระดูก',
    'Bone tracks':'แทร็กกระดูก', 'Take':'เทก', 'frames':'เฟรม',
    'Select a bone to edit its keyframes.':'เลือกกระดูกเพื่อแก้คีย์เฟรม',
    'A keyframe already exists at the destination frame.':'เฟรมปลายทางมีคีย์อยู่แล้ว',
    'Left drag: seek or move a key. Middle drag: select frames. Double-click: add a key.':
        'ลากซ้ายเพื่อเลื่อนเวลา หรือย้ายคีย์ กดล้อเมาส์ค้างลากเพื่อเลือกช่วง ดับเบิลคลิกเพื่อเพิ่มคีย์',
    'File':'ไฟล์', 'Help':'ช่วยเหลือ', 'Controls':'วิธีควบคุม', 'Exit':'ออกจากโปรแกรม',
    'Open Video...':'เปิดวิดีโอ...', 'Open Video':'เปิดวิดีโอ', 'Open video':'เปิดวิดีโอ',
    'Open Project...':'เปิดโครงการ...', 'Open Project Folder':'เปิดโฟลเดอร์โครงการ',
    'Save Project As...':'บันทึกโครงการเป็น...', 'Import Character...':'นำเข้าตัวละคร...',
    'Export':'ส่งออก', 'Export...':'ส่งออก...', 'Export Preview...':'ส่งออกภาพตัวอย่าง...',
    'Check System':'ตรวจสอบระบบ', 'Motion workspace':'พื้นที่สร้างการเคลื่อนไหว',
    'Open a video or drop it into the workspace':'เปิดหรือลากวิดีโอมาวางเพื่อเริ่มงาน',
    'Model Manager':'จัดการโมเดล', '? Model Guide':'? คู่มือโมเดล',
    'AI Motion Model':'โมเดล AI', 'Movie Clip':'วิดีโอต้นฉบับ', '3D Viewport':'มุมมอง 3D',
    'No clip loaded':'ยังไม่มีวิดีโอ', 'People':'บุคคล', 'Stream':'ส่งกระดูก',
    'Overlays':'ภาพซ้อน', 'Bone Overlay':'แสดงกระดูก', 'Frame All':'พอดีทั้งหมด',
    'Timeline':'ไทม์ไลน์', 'Timeline Help':'วิธีใช้ไทม์ไลน์', 'Clip: no video':'คลิป: ยังไม่มีวิดีโอ',
    'Trim clips · review motion · edit contacts':'ตัดช่วงคลิป · ตรวจท่าทาง · แก้จุดสัมผัส',
    'Reset Locks':'คืนค่าการยึด', 'Reset Trim':'คืนช่วงคลิป', 'Find person':'ค้นหาบุคคล',
    'Default':'ค่าเริ่มต้น', 'Camera':'กล้อง', 'Static Camera':'กล้องคงที่',
    'Moving Camera / SimpleVO':'กล้องเคลื่อนที่ / SimpleVO', 'Refine Camera Rotation':'ปรับมุมกล้องละเอียด',
    'Smooth Motion':'ลดการสั่น', 'Motion Correction':'แก้ไขการเคลื่อนไหว',
    'Enable Correction':'เปิดการแก้ไข', 'Correction Mode':'รูปแบบการแก้ไข',
    'Flat Ground':'พื้นราบ', 'Multi-level':'พื้นหลายระดับ', 'Foot':'เท้า', 'Hand':'มือ',
    'Lock Preset':'รูปแบบการยึด', 'Normal':'ปกติ', 'Soft':'นุ่มนวล', 'Strong':'เข้มงวด',
    'Ground Contact / Correction Floor':'จุดสัมผัสและระดับพื้น', 'Auto Floor Height':'หาระดับพื้นอัตโนมัติ',
    'Floor Height (World Y)':'ระดับพื้น (แกน Y)', 'Pelvis Height Offset (from Auto)':'ชดเชยความสูงเชิงกราน',
    'Apply Correction':'ใช้การแก้ไข', 'Processing Resources':'ทรัพยากรประมวลผล',
    'Resource Mode':'โหมดทรัพยากร', 'Resource Safety':'ป้องกันหน่วยความจำเต็ม',
    'Automatic':'อัตโนมัติ', 'Low Memory':'ประหยัดหน่วยความจำ',
    'Reconstruct 3D':'สร้างการเคลื่อนไหว 3D', 'Prepare Preview':'เตรียมภาพตัวอย่าง',
    'Cancel Job':'ยกเลิกงาน', 'Analyze 2D':'วิเคราะห์ 2D', 'Console':'บันทึกการทำงาน',
    'Ready. Open a video or a project.':'พร้อมใช้งาน เปิดวิดีโอหรือโครงการเพื่อเริ่ม',
    'Floor Grid':'ตารางพื้น', 'Correction Floor':'พื้นแก้ไข', 'Motion Path':'เส้นทางเคลื่อนไหว',
    'Lock':'จุดยึด', 'Name':'ชื่อ', 'Follow Actor':'ติดตามบุคคล',
    'Light':'สว่าง', 'Dark':'มืด', 'Appearance':'รูปแบบหน้าตา',
    'Light appearance':'หน้าตาโทนสว่าง', 'Dark appearance':'หน้าตาโทนมืด',
    'Model':'โมเดล', 'Status':'สถานะ', 'Action':'การทำงาน', 'Ready':'พร้อม', 'Missing':'ยังไม่มี',
    'Auto Download':'ดาวน์โหลดอัตโนมัติ', 'Manual Download...':'วิธีดาวน์โหลด...',
    'Import...':'นำเข้า...', 'Import':'นำเข้า', 'Download All':'ดาวน์โหลดทั้งหมด',
    'Open Download Page':'เปิดหน้าดาวน์โหลด', 'Runtime Setup...':'ติดตั้งสภาพแวดล้อม...',
    'Ready to download or import models.':'พร้อมดาวน์โหลดหรือนำเข้าไฟล์โมเดล',
    'Close':'ปิด', 'Cancel':'ยกเลิก', 'Continue...':'ถัดไป...', 'Save':'บันทึก',
    'Format':'รูปแบบไฟล์', 'BVH profile':'รูปแบบกระดูก BVH', 'Generic / Blender':'ทั่วไป / Blender',
    'Frame range':'ช่วงเฟรม', 'All frames':'ทุกเฟรม', 'Selected frames':'เลือกช่วงเฟรม',
    'Start frame':'เฟรมเริ่ม', 'End frame':'เฟรมจบ',
    'Clear selection':'ล้างช่วงที่เลือก',
    'Left drag on frame numbers: seek. Middle drag: select frames for FBX export. Escape clears the selection.':
        'ลากเมาส์ซ้ายบนตัวเลขเฟรมเพื่อเลื่อนเวลา กดล้อเมาส์ค้างแล้วลากเพื่อเลือกช่วงส่งออก FBX กด Escape เพื่อล้างช่วงที่เลือก',
    'Left-click or left-drag the frame ruler or blue frame-number box to seek.':
        'คลิกซ้ายหรือลากเมาส์ซ้ายบนแถวตัวเลขเฟรมหรือกล่องเฟรมสีน้ำเงินเพื่อเลื่อนเวลา',
    'Wheel: zoom | Shift + wheel or MMB on tracks: pan':
        'หมุนล้อเมาส์เพื่อซูม | Shift + ล้อเมาส์ หรือกดล้อเมาส์ค้างลากบนแทร็กเพื่อเลื่อนมุมมอง',
    'Middle-drag across the frame numbers: select a frame range for FBX export. Escape: clear selection.':
        'กดล้อเมาส์ค้างแล้วลากบนตัวเลขเฟรมเพื่อเลือกช่วงส่งออก FBX กด Escape เพื่อล้างช่วงที่เลือก',
    'Left-click or left-drag the frame ruler or blue frame box to seek':
        'คลิกซ้ายหรือลากเมาส์ซ้ายบนแถวตัวเลขเฟรมหรือกล่องเฟรมสีน้ำเงินเพื่อเลื่อนเวลา',
    'MMB-drag on frame numbers selects an FBX export range':
        'กดล้อเมาส์ค้างแล้วลากบนตัวเลขเฟรมเพื่อเลือกช่วงส่งออก FBX',
    'Wheel to zoom; MMB on tracks or Shift+wheel to pan; Reset Trim restores the full clip':
        'หมุนล้อเมาส์เพื่อซูม กดล้อเมาส์ค้างลากบนแทร็กหรือ Shift + ล้อเมาส์เพื่อเลื่อนมุมมอง คืนช่วงคลิปเพื่อใช้คลิปเต็ม',
    'The selected frames do not contain saved motion.':'ช่วงเฟรมนี้ไม่มีการเคลื่อนไหวที่บันทึกไว้',
    'The selected frames do not contain character motion.':'ช่วงเฟรมนี้ไม่มีการเคลื่อนไหวของตัวละคร',
    'FBX Compatibility (Maya)':'FBX ที่เข้ากันได้กับ Maya', 'Add T-pose before motion':'เพิ่มท่า T-pose ก่อนเริ่ม',
    'Place at origin':'เริ่มที่จุดกำเนิด', 'Symmetrical rest pose':'ท่าพักกระดูกสมมาตร',
    'Export saved camera tracking':'ส่งออกการเคลื่อนกล้อง',
    'Frame':'เฟรม', 'Video':'วิดีโอ', 'Motion':'ท่าทาง',
    'L foot':'เท้าซ้าย', 'R foot':'เท้าขวา', 'L hand':'มือซ้าย', 'R hand':'มือขวา',
    'Disabled':'ปิดใช้งาน', 'Apply Correction to generate locks':'ใช้การแก้ไขเพื่อสร้างจุดยึด',
    'No motion data':'ยังไม่มีข้อมูลการเคลื่อนไหว', 'Body animation':'ท่าทางร่างกาย', 'Source clip':'คลิปต้นฉบับ',
    'PEAR live preview — no recording':'ภาพสด PEAR — ไม่บันทึกการเคลื่อนไหว',
    'Open a video to begin\nMP4 · MOV · AVI':'เปิดวิดีโอเพื่อเริ่มงาน\nMP4 · MOV · AVI',
    'Open a video to begin':'เปิดวิดีโอเพื่อเริ่มงาน',
    'No motion loaded\n\nReconstruct a motion or open a project\nto compare the initial and refined animation.':
        'ยังไม่มีการเคลื่อนไหว\n\nสร้างการเคลื่อนไหวหรือเปิดโครงการ\nเพื่อดูและเปรียบเทียบผลก่อนและหลังแก้ไข',
    'User Perspective':'มุมมองอิสระ',
    'LMB: Orbit  |  MMB / RMB: Pan  |  Wheel: Zoom  |  Double-click: Frame':
        'เมาส์ซ้าย: หมุน  |  กลาง/ขวา: เลื่อน  |  ลูกล้อ: ซูม  |  ดับเบิลคลิก: พอดีภาพ',
    'Person Identity / OSNet':'แยกตัวบุคคล / OSNet', 'Actor Detection / YOLO':'ตรวจจับบุคคล / YOLO',
    'Hand Features / HaMeR':'วิเคราะห์มือ / HaMeR', 'HaMeR mean parameters':'พารามิเตอร์อ้างอิง HaMeR',
    'Motion / ExMR':'สร้างการเคลื่อนไหว / ExMR', 'ExMR configuration':'การตั้งค่า ExMR',
    'Body / Hand / Foot Keypoints / Sapiens2 1B':'จุดร่างกาย มือ และเท้า / Sapiens2 1B',
    'SAM 3.1 Person Tracking (Optional)':'ติดตามบุคคลด้วย SAM 3.1 (ตัวเลือกเสริม)',
    'Body Model / SMPL-X Neutral':'รูปร่างอ้างอิง / SMPL-X Neutral',
    'Hand Model / MANO Right':'รูปร่างมืออ้างอิง / MANO Right',
    'Another task is running. You can still open manual download instructions.':
        'มีงานอื่นกำลังทำงานอยู่ คุณยังเปิดวิธีดาวน์โหลดได้',
    'Use Auto Download for public files, or Manual Download and Import for any model.':
        'ใช้ดาวน์โหลดอัตโนมัติสำหรับไฟล์สาธารณะ หรือเปิดวิธีดาวน์โหลดแล้วนำเข้าไฟล์',
    'Registered body model files are not redistributed by this app.':
        'ไฟล์รูปร่างที่ต้องลงทะเบียนต้องดาวน์โหลดจากผู้ให้บริการเอง',
    'Choose a video to create motion from.':'เลือกวิดีโอสำหรับสร้างการเคลื่อนไหว',
    'Open saved motion and settings without reconstructing the video.':'เปิดผลและการตั้งค่าที่บันทึกไว้',
    'Close RGB MoCap.':'ปิดโปรแกรม RGB MoCap',
    'Check hardware and required software. Results appear in the Console.':'ตรวจฮาร์ดแวร์และซอฟต์แวร์ ดูผลในบันทึกการทำงาน',
    'Show keyboard shortcuts and workspace controls.':'แสดงปุ่มลัดและวิธีควบคุม',
    'Prepare model files for the selected motion model.':'เตรียมไฟล์สำหรับโมเดลที่เลือก',
    'Download or import the files needed by the selected AI model.':'ดาวน์โหลดหรือนำเข้าไฟล์ที่โมเดล AI ต้องใช้',
    'Fit all visible people in the 3D view.':'แสดงบุคคลทั้งหมดให้พอดีมุมมอง 3D',
    'Show or hide processing details and error messages.':'แสดงหรือซ่อนรายละเอียดและข้อผิดพลาด',
    'Stop the current processing queue. Completed results are kept.':'หยุดคิวประมวลผล โดยเก็บผลที่เสร็จแล้ว',
    'Use light appearance. Saved on this computer.':'ใช้หน้าตาโทนสว่าง และจำตัวเลือกไว้ในเครื่องนี้',
    'Use dark appearance. Saved on this computer.':'ใช้หน้าตาโทนมืด และจำตัวเลือกไว้ในเครื่องนี้',
    'Start Live Tracking':'เริ่มติดตามสด', 'Stop Live Tracking':'หยุดติดตามสด',
    'Reset Bones':'ตั้งค่ากระดูกใหม่', 'Camera Align':'จัดแนวกล้อง', 'World Position':'ตำแหน่งในโลก',
    'One Euro Filter':'ตัวกรอง One Euro', 'Rotation':'การหมุน', 'Count':'จำนวน', 'Refresh':'รีเฟรช',
    'Motion Model Guide':'คู่มือโมเดลการเคลื่อนไหว', 'Workspace Controls':'วิธีควบคุมพื้นที่ทำงาน',
    'No motion loaded':'ยังไม่มีการเคลื่อนไหว',
    'Reconstruct a motion or open a project':'สร้างการเคลื่อนไหวหรือเปิดโครงการ',
    'to compare the initial and refined animation.':'เพื่อเปรียบเทียบผลก่อนและหลังแก้ไข',
    'Choose contact strength. Normal is the starting point. Apply Correction to update; manually edited timings stay unchanged.':
        'เลือกระดับการยึด เริ่มจากปกติ แล้วกดใช้การแก้ไข ช่วงเวลาที่แก้เองจะยังคงเดิม',
    'Estimate floor height from the motion. Turn off to enter the height yourself.':
        'ประมาณระดับพื้นจากการเคลื่อนไหว ปิดเพื่อกำหนดระดับเอง',
    'Floor height in meters along the vertical Y axis. Turn off Auto Floor Height to edit. The gray reference grid stays at zero.':
        'ระดับพื้นหน่วยเมตรตามแกน Y ปิดหาระดับพื้นอัตโนมัติเพื่อแก้ไข ตารางอ้างอิงยังอยู่ที่ศูนย์',
    'Create 3D motion for checked people in the trimmed video range using the selected model and settings. Reuses valid completed steps.':
        'สร้างท่าทาง 3D ให้บุคคลที่เลือกในช่วงคลิป โดยใช้โมเดลและการตั้งค่าปัจจุบัน พร้อมใช้ขั้นตอนที่เสร็จแล้วและยังใช้ได้',
    'Prepare the 3D mesh and skeleton from the selected motion result. Available after reconstruction; does not run AI inference again.':
        'เตรียมพื้นผิวและกระดูก 3D จากผลที่เลือก ใช้ได้หลังสร้างการเคลื่อนไหว โดยไม่ประมวลผล AI ใหม่',
    'Update contact correction using these settings and timeline timings. Rebuilds the preview and export without running the AI model again.':
        'ปรับจุดสัมผัสตามการตั้งค่าและช่วงเวลาบนไทม์ไลน์ อัปเดตภาพตัวอย่างและผลส่งออกโดยไม่รัน AI ใหม่',
    'Automatic uses the fast path when memory is available and switches supported stages to Low Memory when needed. Low Memory uses CPU loading and offloading; it can be slower and use more RAM. Model precision and video frames are unchanged.':
        'อัตโนมัติใช้วิธีเร็วเมื่อมีหน่วยความจำพอ และเปลี่ยนเป็นโหมดประหยัดตามขั้นตอนที่รองรับ โหมดประหยัดใช้ CPU ช่วยโหลด จึงอาจช้าลงและใช้ RAM มากขึ้น ความละเอียดการคำนวณและจำนวนเฟรมคงเดิม',
    'Stop when RAM headroom is low and limit VRAM allocation. Disable to bypass these limits; actual memory shortages may cause processing failure or system slowdowns. Automatic batching, Low Memory and OOM recovery remain enabled.':
        'หยุดเมื่อ RAM เหลือน้อยและจำกัดการใช้ VRAM หากปิดจะไม่ใช้ข้อจำกัดนี้ หน่วยความจำไม่พออาจทำให้งานล้มเหลวหรือระบบช้า การจัดชุดอัตโนมัติ โหมดประหยัด และการกู้คืนเมื่อหน่วยความจำเต็มยังทำงานอยู่',
    'Download this file automatically. If it fails, use Manual Download or Import an existing copy.':
        'ดาวน์โหลดไฟล์นี้อัตโนมัติ หากไม่สำเร็จให้ดูวิธีดาวน์โหลดหรือนำเข้าไฟล์ที่มีอยู่',
    'Show download links and instructions. Download in your browser, then use Import in the instructions or this row.':
        'แสดงลิงก์และวิธีดาวน์โหลด ดาวน์โหลดในเบราว์เซอร์แล้วนำเข้าไฟล์ในหน้าคำแนะนำหรือแถวนี้',
    'Choose a model file you already downloaded. The app checks it before replacing any existing file.':
        'เลือกไฟล์โมเดลที่ดาวน์โหลดแล้ว โปรแกรมจะตรวจสอบก่อนแทนที่ไฟล์เดิม',
}

REVERSE_TH = {translated: source for source, translated in TH.items()}


def source_text(text):
    """Recover UI text already translated by a dynamic caller."""
    return REVERSE_TH.get(text, text)


def language():
    app = QApplication.instance()
    return app.property('uiLanguage') if app and app.property('uiLanguage') in ('en','th') else 'en'


def tr(text):
    if language() != 'th' or not isinstance(text, str):
        return text
    if text in TH:
        return TH[text]
    match = re.fullmatch(r'(.+): (\d+)/(\d+) models ready', text)
    if match:
        return f'{match[1]}: พร้อม {match[2]}/{match[3]} ไฟล์'
    match = re.fullmatch(r'Warning: (\d+) required models? missing\.', text)
    if match:
        return f'ยังขาดไฟล์ที่จำเป็น {match[1]} รายการ'
    if text == 'Open Model Manager to download or import.':
        return 'เปิดจัดการโมเดลเพื่อดาวน์โหลดหรือนำเข้า'
    if text.endswith(' Settings'):
        return 'การตั้งค่า ' + text[:-9]
    if text.endswith(' Models'):
        return 'ไฟล์โมเดล ' + text[:-7]
    if text.endswith(' Model Manager'):
        return 'จัดการโมเดล ' + text[:-14]
    if text.startswith('Models for ') and text.endswith(' and compatible add-ons.'):
        return 'ไฟล์สำหรับ ' + text[len('Models for '):-len(' and compatible add-ons.')] + ' และส่วนเสริมที่รองรับ'
    if '\n' in text:
        return '\n'.join(tr(line) for line in text.split('\n'))
    return text


class Localizer(QObject):
    changed = Signal(str)

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.pending = False
        self.applying = False
        app.installEventFilter(self)

    def eventFilter(self, obj, event):
        if not self.applying and event.type() in (QEvent.Show, QEvent.Polish, QEvent.LayoutRequest,
                                                   QEvent.ToolTipChange, QEvent.WindowTitleChange):
            self.schedule()
        return False

    def schedule(self):
        if not self.pending:
            self.pending = True
            QTimer.singleShot(0, self.apply)

    def field(self, obj, key, getter, setter, transform=tr):
        current = getter()
        key = str(key)
        records = obj.property('_i18nFields') or {}
        source, previous = records.get(key, (source_text(current), current))
        if current != previous:
            source = source_text(current)
        translated = transform(source)
        pair = [source, translated]
        if records.get(key) != pair:
            records[key] = pair
            obj.setProperty('_i18nFields', records)
        if translated != current:
            blocked = obj.blockSignals(True)
            try:
                setter(translated)
            finally:
                obj.blockSignals(blocked)

    def apply(self):
        self.pending = False
        if self.applying:
            return
        self.applying = True
        try:
            for widget in self.app.allWidgets():
                if isinstance(widget, (QLabel, QAbstractButton)):
                    if not widget.property('i18nDataText') or widget.text() in (TH['Open a video or drop it into the workspace'], 'Open a video or drop it into the workspace'):
                        self.field(widget, 'text', widget.text, widget.setText)
                elif isinstance(widget, QGroupBox):
                    self.field(widget, 'title', widget.title, widget.setTitle)
                if isinstance(widget, QTabBar):
                    for index in range(widget.count()):
                        self.field(widget, ('tab',index), lambda i=index:widget.tabText(i), lambda t,i=index:widget.setTabText(i,t))
                if isinstance(widget, QComboBox) and not widget.property('i18nSkipItems'):
                    for index in range(widget.count()):
                        data = widget.itemData(index)
                        if isinstance(data, str) and ('/' in data or '\\' in data or ':' in data):
                            continue
                        self.field(widget, ('item',index), lambda i=index:widget.itemText(i), lambda t,i=index:widget.setItemText(i,t))
                if isinstance(widget, QTableWidget) and type(widget.parentWidget()).__name__ == 'ModelsDialog':
                    for column in range(widget.columnCount()):
                        item=widget.horizontalHeaderItem(column)
                        if item:
                            self.field(widget, ('header',column), item.text, item.setText)
                    for row in range(widget.rowCount()):
                        for column in (0,1):
                            item=widget.item(row,column)
                            if item:
                                self.field(widget, ('cell',row,column), item.text, item.setText)
                if isinstance(widget, QTextBrowser) and widget.property('i18nPlainText'):
                    self.field(widget, 'plainText', widget.toPlainText, widget.setPlainText)
                self.field(widget, 'tooltip', widget.toolTip, widget.setToolTip, translate_tooltip)
                if widget.isWindow():
                    self.field(widget, 'windowTitle', widget.windowTitle, widget.setWindowTitle)
                for action in widget.actions():
                    self.field(action, 'text', action.text, action.setText)
                    self.field(action, 'tooltip', action.toolTip, action.setToolTip, translate_tooltip)
        finally:
            self.applying = False


def translate_tooltip(text):
    from .tooltips import plain_tooltip, tooltip_text
    plain = plain_tooltip(text)
    translated = tr(plain)
    return tooltip_text(translated) if translated != plain else text


def localizer(app=None):
    app = app or QApplication.instance()
    if not hasattr(app, '_mocap_localizer'):
        app._mocap_localizer = Localizer(app)
    return app._mocap_localizer


def set_language(value, *, persist=True):
    if value not in ('en', 'th'):
        raise ValueError('Unsupported UI language')
    app = QApplication.instance()
    app.setProperty('uiLanguage', value)
    controller = localizer(app)
    controller.apply()
    controller.changed.emit(value)
    for widget in app.allWidgets():
        QWidget.update(widget)
    if persist:
        from .resource_safety import path, read_settings, MAX_BYTES
        from .storage import atomic_json
        try:
            target = path()
            settings = read_settings(target)
            settings['language'] = value
            if len(json.dumps(settings, ensure_ascii=False, indent=2).encode('utf-8')) > MAX_BYTES:
                raise ValueError('Local settings exceed the size limit.')
            atomic_json(target, settings)
        except (OSError, ValueError) as exc:
            print('Language preference could not be saved: ' + str(exc), flush=True)


def configure_language(app):
    from .resource_safety import path, read_settings
    try:
        value = read_settings(path()).get('language', 'en')
    except (OSError, ValueError):
        value = 'en'
    set_language(value if value in ('en','th') else 'en', persist=False)


class LanguageSelector(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('i18nSkipItems', True)
        self.setAccessibleName('Language / ภาษา')
        self.setToolTip('Language / ภาษา')
        self.addItem('English', 'en')
        self.addItem('ไทย', 'th')
        self.setMinimumContentsLength(5)
        self.setCurrentIndex(self.findData(language()))
        self.currentIndexChanged.connect(self.choose)
        localizer().changed.connect(self.sync)

    def choose(self, index):
        set_language(self.itemData(index))

    def sync(self, value):
        blocked = self.blockSignals(True)
        self.setCurrentIndex(self.findData(value))
        self.blockSignals(blocked)
