# ฟอนต์สำหรับ RGB MoCap

ฟอนต์ที่เพิ่มสำหรับ UI ใช้ไฟล์จาก [Google Fonts](https://github.com/google/fonts/tree/29b4ec6df2522a8aee279414b78a07910b065874) โดยตรง ที่ commit `29b4ec6df2522a8aee279414b78a07910b065874` และเก็บใบอนุญาต SIL Open Font License 1.1 ของแต่ละชุดไว้ข้างไฟล์ ฟอนต์ไม่ได้ติดตั้งลง Windows และไม่ได้แก้ไขข้อมูลภายใน มีเพียงชื่อไฟล์ปลายทางที่ปรับให้เรียกใช้ง่าย

| ไฟล์ในโปรเจกต์ | Family | ต้นฉบับที่ commit ข้างต้น | ใบอนุญาต |
| --- | --- | --- | --- |
| `Manrope-Variable.ttf` | Manrope | `ofl/manrope/Manrope[wght].ttf` | `MANROPE-OFL.txt` |
| `NotoSansThai-Variable.ttf` | Noto Sans Thai | `ofl/notosansthai/NotoSansThai[wdth,wght].ttf` | `NOTOSANSTHAI-OFL.txt` |

Manrope ใช้น้ำหนัก 200–800 สำหรับข้อความอังกฤษและตัวเลข ส่วน Noto Sans Thai มีน้ำหนัก 100–900 และแกนความกว้าง 62.5–100 สำหรับอักษรไทย ใช้ลำดับ family `Manrope`, `Noto Sans Thai`, `Segoe UI` เพื่อให้ Qt เลือกฟอนต์ไทยเมื่อข้อความผสมกัน

## การตรวจสอบไฟล์

| ไฟล์ | ขนาด (bytes) | SHA-256 |
| --- | ---: | --- |
| `Manrope-Variable.ttf` | 164700 | `3ae11c49db0455a3cc33e37d380f20fdb8c7f8b41dc07625c177e3d87a9d6ae6` |
| `NotoSansThai-Variable.ttf` | 218652 | `5a1c559bb539583c8a1fd99d1c5b9491e5e14478c9cd2bd0970d5c3096cc9ef8` |
| `MANROPE-OFL.txt` | 4387 | `58172e0c0fac2cda8a37b348164bb55e44b0e69051e557e92b1d3f6910141f7b` |
| `NOTOSANSTHAI-OFL.txt` | 4380 | `2e98fd23a52d253db8612cd5942c8f2ff4111b21d2367050fdca91d8ccc374a0` |

ตรวจ Git blob SHA-1 ของทั้งสี่ไฟล์แล้วตรงกับ Google Fonts API ที่ revision นี้ ทดสอบโหลดด้วย `QFontDatabase.addApplicationFont` บน Qt offscreen ผ่าน ตรวจ Latin glyphs ของทั้งสองฟอนต์และ Thai glyphs ของ Noto Sans Thai ผ่าน และ `QTextLayout` เลือกทั้ง Manrope และ Noto Sans Thai จริงสำหรับข้อความผสม `RGB MoCap ภาษาไทย ผู้ใช้งาน 123`

`NotoSansKR.ttf` และ `OFL.txt` เป็นไฟล์เดิมของโปรเจกต์และยังคงไว้ตามเดิม
