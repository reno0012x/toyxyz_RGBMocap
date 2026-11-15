"""Local Light/Dark appearance for the Qt workspace; independent of processing."""
from __future__ import annotations

import json
from PySide6.QtCore import QObject, QLocale, QPointF, Signal, Qt, QEvent
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap, QPolygonF
from .paths import ROOT

COLORS = {
    'dark': dict(window='#101010', surface='#191919', raised='#222222', field='#282828',
                 hover='#303030', pressed='#151515', border='#353535', divider='#292929',
                 text='#f2f2f2', secondary='#b0b0b0', muted='#8c8c8c', disabled='#737373',
                 accent='#2a70d4', accent_hover='#2365c4', selection='#243b59',
                 warning='#f4bd68', error='#ff8787', success='#80c7a0', link='#8dbaff'),
    'light': dict(window='#ececee', surface='#f6f6f7', raised='#ffffff', field='#ffffff',
                  hover='#e6e6e9', pressed='#dadade', border='#d0d0d5', divider='#dedee2',
                  text='#202023', secondary='#55555d', muted='#686870', disabled='#818189',
                  accent='#246bd6', accent_hover='#185bbd', selection='#dce9fc',
                  warning='#8a5108', error='#b52e38', success='#247044', link='#175fbf'),
}
COLORS['dark'].update(canvas='#151515', canvas_text='#dedede', canvas_muted='#999999',
                      grid_minor='#292929', grid_major='#3b3b3b', rail='#1c1c1c', track='#222222')
COLORS['light'].update(canvas='#f7f8fa', canvas_text='#303744', canvas_muted='#616c7a',
                       grid_minor='#e6e9ee', grid_major='#cdd3dd', rail='#edf0f5', track='#ffffff')


def current_theme(app=None):
    if app is None:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
    return app.property('appearance') if app and app.property('appearance') in COLORS else 'dark'


def color(name, mode=None):
    return COLORS[mode or current_theme()][name]


def stylesheet(mode):
    c = COLORS[mode]
    css = r'''
QWidget { color:@text; font-size:13px; }
QMainWindow,QDialog { background:@window; }
QLabel { background:transparent; }
QLabel#brand { font-size:19px; font-weight:600; letter-spacing:-0.4px; }
QLabel#workspaceSubtitle { color:@muted; font-size:11px; }
QLabel#muted { color:@muted; }
QLabel#status { color:@secondary; padding:4px 2px; font-size:12px; }
QLabel#taskInfo { color:@link; padding:4px; font-size:12px; }
QLabel[tone="warning"] { color:@warning; }
QLabel[tone="error"] { color:@error; }
QLabel[tone="success"] { color:@success; }
QFrame#workspaceToolbar { background:@surface; border:1px solid @divider; border-radius:12px; }
QFrame#editor { background:@surface; border:1px solid @border; border-radius:10px; }
QWidget#editorHeader { background:@surface; border:0; border-bottom:1px solid @divider; }
QWidget#editorHeader QLabel,QWidget#editorHeader QCheckBox { font-size:11px; }
QWidget#editorHeader QPushButton,QWidget#editorHeader QComboBox,QWidget#editorHeader QAbstractSpinBox { font-size:11px; padding:3px 6px; min-height:16px; }
QWidget#modelSidebar,QStackedWidget#modelPages,QWidget[motion_tool],
QWidget#modelSettingsViewport { background:@surface; }
QWidget#modelSidebar { border-radius:12px; }
QFrame#modelActions { background:@surface; border-top:1px solid @divider; padding-top:10px; }
QTabWidget#peopleTabs::pane { background:@surface; border:0; }
QTabBar::tab { background:transparent; color:@muted; border:0; padding:7px 12px; margin:3px; border-radius:6px; }
QTabBar::tab:hover { background:@hover; color:@text; }
QTabBar::tab:selected { background:@raised; color:@text; font-weight:600; }
QGroupBox { border:0; border-bottom:1px solid @divider; margin-top:21px; padding:10px 2px 14px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:2px; padding:0; color:@secondary; font-size:12px; }
QPushButton,QToolButton { background:@field; border:1px solid @border; border-radius:7px; padding:6px 10px; min-height:18px; }
QPushButton:hover,QToolButton:hover { background:@hover; border-color:@muted; }
QPushButton:pressed,QToolButton:pressed { background:@pressed; }
QPushButton:focus,QToolButton:focus { border:1px solid @accent; }
QPushButton:disabled,QToolButton:disabled { color:@disabled; background:@surface; border-color:@divider; }
QPushButton#primary { background:@accent; border-color:@accent; color:#ffffff; font-weight:600; padding:9px 12px; }
QPushButton#primary:hover { background:@accent_hover; border-color:@accent_hover; }
QPushButton#primary:pressed { background:@accent; }
QPushButton#primary:disabled { background:@hover; border-color:@divider; color:@disabled; }
QPushButton#transport { padding:3px 5px; min-width:24px; min-height:18px; }
QToolButton#toolbarAction { background:transparent; border-color:transparent; padding:6px 10px; }
QToolButton#toolbarAction:hover { background:@hover; border-color:@border; }
QFrame#appearanceSwitch { background:@window; border:1px solid @divider; border-radius:8px; }
QToolButton#appearanceOption { background:transparent; border:1px solid transparent; border-radius:5px; padding:3px 10px; font-size:11px; color:@muted; }
QToolButton#appearanceOption:checked { background:@raised; border-color:@border; color:@text; }
QToolButton#appearanceOption:focus { border-color:@accent; }
QToolButton#cameraThumbnail { background:@field; border:1px solid @border; padding:3px; }
QToolButton#cameraThumbnail:checked { border:2px solid @accent; background:@selection; }
QComboBox,QAbstractSpinBox,QLineEdit { background:@field; border:1px solid @border; border-radius:6px; padding:4px 7px; min-height:20px; selection-background-color:@accent; selection-color:#ffffff; }
QComboBox:hover,QAbstractSpinBox:hover,QLineEdit:hover { border-color:@muted; }
QComboBox:focus,QAbstractSpinBox:focus,QLineEdit:focus { border-color:@accent; }
QComboBox:disabled,QAbstractSpinBox:disabled,QLineEdit:disabled { background:@surface; color:@disabled; border-color:@divider; }
QComboBox::drop-down { border:0; width:20px; }
QComboBox::down-arrow { image:url("CHEVRON_ICON"); width:12px; height:12px; }
QComboBox QAbstractItemView { background:@raised; color:@text; selection-background-color:@selection; selection-color:@text; border:1px solid @border; padding:4px; outline:0; }
QCheckBox { spacing:7px; padding:2px 0; }
QCheckBox:disabled { color:@disabled; }
QCheckBox::indicator { width:15px; height:15px; border:1px solid @muted; border-radius:4px; background:@field; }
QCheckBox::indicator:hover { border-color:@accent; background:@selection; }
QCheckBox::indicator:checked { background:@accent; border-color:@accent; image:url("CHECK_ICON"); }
QCheckBox::indicator:disabled { border-color:@border; background:@hover; }
QCheckBox:focus { color:@link; }
QRadioButton { spacing:7px; }
QRadioButton::indicator { width:14px; height:14px; border:1px solid @muted; border-radius:8px; background:@field; }
QRadioButton::indicator:checked { border:4px solid @accent; background:@field; }
QListWidget { background:@surface; border:0; border-radius:7px; outline:0; }
QListWidget::item { min-height:27px; padding:3px; border-radius:5px; }
QListWidget::item:selected { background:@selection; color:@text; }
QListWidget::item:hover { background:@hover; }
QListWidget::indicator { width:15px; height:15px; border:1px solid @muted; border-radius:4px; background:@field; }
QListWidget::indicator:checked { background:@accent; border-color:@accent; image:url("CHECK_ICON"); }
QProgressBar { background:@divider; border:0; border-radius:2px; min-height:4px; }
QProgressBar::chunk { background:@accent; border-radius:2px; }
QTextEdit,QPlainTextEdit,QTextBrowser,QTableWidget { background:@raised; color:@text; border:1px solid @divider; border-radius:8px; selection-background-color:@selection; selection-color:@text; }
QTextBrowser { padding:8px; }
QTextBrowser[tone="error"] { color:@error; }
QTextEdit#console { font-family:"Cascadia Code","Consolas"; font-size:12px; padding:9px; }
QTableWidget { gridline-color:@divider; alternate-background-color:@surface; }
QTableWidget::item { padding:6px; }
QTableWidget::item:selected { background:@selection; color:@text; }
QTableWidget QPushButton { font-size:12px; padding:5px 8px; }
QHeaderView::section { background:@surface; color:@secondary; border:0; border-bottom:1px solid @divider; padding:9px 6px; font-weight:600; font-size:12px; }
QMenuBar { background:@window; border:0; padding:2px 5px; }
QMenuBar::item { padding:5px 10px; border-radius:5px; }
QMenuBar::item:selected { background:@hover; }
QMenu { background:@raised; border:1px solid @border; padding:5px; }
QMenu::item { padding:7px 25px; border-radius:4px; }
QMenu::item:selected { background:@accent; color:#ffffff; }
QMenu::item:disabled { color:@disabled; }
QMenu::separator { height:1px; background:@divider; margin:5px 8px; }
QSplitter::handle { background:@window; }
QSplitter::handle:hover { background:@border; }
QScrollArea { background:@surface; border:0; }
QScrollBar:vertical { width:8px; background:transparent; margin:2px; }
QScrollBar::handle:vertical { background:@border; border-radius:3px; min-height:28px; }
QScrollBar::handle:vertical:hover { background:@muted; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QScrollBar:horizontal { height:8px; background:transparent; }
QScrollBar::handle:horizontal { background:@border; min-width:28px; border-radius:3px; }
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width:0; }
QToolTip { background:@raised; color:@text; border:1px solid @border; padding:7px; }
'''
    for name in sorted(c, key=len, reverse=True):
        css = css.replace('@' + name, c[name])
    return (css.replace('CHECK_ICON', (ROOT/'assets/icons/check.svg').as_posix())
            .replace('CHEVRON_ICON', (ROOT/f'assets/icons/chevron-{mode}.svg').as_posix()))


STYLE = stylesheet('dark')


class Appearance(QObject):
    changed = Signal(str)

    def __init__(self, app):
        super().__init__(app)
        app.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtWidgets import QWidget
        if event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            native_titlebar(obj, current_theme())
        return False


def native_titlebar(widget, mode):
    """Set only this application's DWM frame; leave Windows preferences alone."""
    from PySide6.QtWidgets import QApplication
    if QApplication.platformName() != 'windows' or widget.windowHandle() is None:
        return
    import ctypes
    try:
        value = ctypes.c_int(mode == 'dark')
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(int(widget.winId())),
                                                  20, ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError):
        pass


def appearance(app=None):
    if app is None:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
    if not hasattr(app, '_mocap_appearance'):
        app._mocap_appearance = Appearance(app)
    return app._mocap_appearance


def set_tone(widget, tone=''):
    if widget.property('tone') == tone:
        return
    widget.setProperty('tone', tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def themed_html(html):
    return html.replace('#84c9ff', color('link')).replace('#8ed2ff', color('link'))


def set_theme(app, mode, *, persist=True):
    if mode not in COLORS:
        raise ValueError('Unknown appearance: ' + str(mode))
    c = COLORS[mode]
    app.setProperty('appearance', mode)
    palette = QPalette()
    roles = {'Window':'surface', 'WindowText':'text', 'Base':'raised', 'AlternateBase':'surface',
             'Text':'text', 'Button':'field', 'ButtonText':'text', 'Highlight':'accent',
             'HighlightedText':None, 'ToolTipBase':'raised', 'ToolTipText':'text',
             'PlaceholderText':'muted', 'Link':'link', 'LinkVisited':'link', 'BrightText':'error',
             'Light':'raised', 'Midlight':'hover', 'Mid':'border', 'Dark':'divider', 'Shadow':'window'}
    for name, token in roles.items():
        palette.setColor(getattr(QPalette, name), QColor(c[token] if token else '#ffffff'))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(c['disabled']))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(mode))
    for widget in app.topLevelWidgets():
        native_titlebar(widget, mode)
    appearance(app).changed.emit(mode)
    if persist:
        from .resource_safety import path, read_settings, MAX_BYTES
        from .storage import atomic_json
        try:
            target = path()
            settings = read_settings(target)
            settings['appearance'] = mode
            if len(json.dumps(settings, ensure_ascii=False, indent=2).encode('utf-8')) > MAX_BYTES:
                raise ValueError('Local settings exceed the size limit.')
            atomic_json(target, settings)
        except (OSError, ValueError) as exc:
            # Appearance still changes for this session; preserve malformed settings.
            print('Appearance preference could not be saved: ' + str(exc), flush=True)


def transport_icon(kind):
    icon = QIcon()
    for state, token in ((QIcon.Normal, 'text'), (QIcon.Disabled, 'disabled')):
        pixmap = QPixmap(32, 32)
        pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color(token)))
        if kind == 'pause':
            painter.drawRoundedRect(4, 3, 3, 10, 0.7, 0.7)
            painter.drawRoundedRect(9, 3, 3, 10, 0.7, 0.7)
        else:
            painter.drawPolygon(QPolygonF([QPointF(4.5, 2.5), QPointF(13, 8), QPointF(4.5, 13.5)]))
        painter.end()
        icon.addPixmap(pixmap, state)
    return icon


def configure_application(app):
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
    app.setStyle('Fusion')
    for filename in ('Manrope-Variable.ttf', 'NotoSansThai-Variable.ttf', 'NotoSansKR.ttf'):
        QFontDatabase.addApplicationFont(str(ROOT/'assets/fonts'/filename))
    font = QFont()
    font.setFamilies(['Manrope', 'Noto Sans Thai', 'Noto Sans KR', 'Segoe UI'])
    font.setPixelSize(13)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    from .resource_safety import path, read_settings
    try:
        mode = read_settings(path()).get('appearance', 'dark')
    except (OSError, ValueError):
        mode = 'dark'
    set_theme(app, mode if isinstance(mode, str) and mode in COLORS else 'dark', persist=False)
    from .i18n import configure_language
    configure_language(app)
