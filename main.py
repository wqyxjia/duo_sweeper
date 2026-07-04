import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QFile, QSettings, QStorageInfo, QTimer, Qt, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scanner import (
    RAW_EXTENSIONS,
    find_unmatched_raw_files,
    get_default_raw_extensions,
    metadata_matching_enabled,
    set_metadata_matching,
    set_raw_extensions,
)
from watcher import FileWatcher
from i18n import get_text, detect_system_language


class ManualDialog(QDialog):
    """用户手册对话框"""

    def __init__(self, main_window, lang: str):
        super().__init__(None)          # ← 彻底无父窗口
        self.setWindowTitle(get_text("manual_title", lang))
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.resize(560, 500)
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(get_text("manual_content", lang))
        # 移除硬编码样式，让 QSS 接管
        layout.addWidget(self.text_edit, 1)

        btn_close = QPushButton(get_text("close_btn", lang))
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

        # 应用主窗口当前主题
        if main_window:
            self.setStyleSheet(main_window.styleSheet())

    def update_language(self, lang):
        self.setWindowTitle(get_text("manual_title", lang))
        self.text_edit.setPlainText(get_text("manual_content", lang))

# 监视模式内部标识（用于逻辑比较，不直接显示）
MODE_ASK = "ask"
MODE_AUTO = "auto"
MODE_BATCH = "batch"

# 监视方向内部标识
DIR_JPG_TO_RAW = "jpg_to_raw"
DIR_RAW_TO_JPG = "raw_to_jpg"
DIR_BOTH = "both"

# JPG 后缀（用于 RAW→JPG 方向时查找对应 JPG）
JPG_SUFFIXES = {".jpg", ".jpeg"}

# ---- 同步目标文件夹配置持久化 ----


def load_sync_targets() -> list[dict]:
    """从 QSettings 加载同步目标文件夹配置，返回副本"""
    settings = QSettings("DuoSweeper", "DuoSweeper")
    raw_list = settings.value("sync_targets", [])
    result: list[dict] = []
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, dict) and "path" in item:
                result.append({
                    "path": item["path"],
                    "enabled": item.get("enabled", True),
                })
    return result


def save_sync_targets(targets: list[dict]) -> None:
    """将同步目标文件夹配置持久化到 QSettings"""
    settings = QSettings("DuoSweeper", "DuoSweeper")
    settings.setValue("sync_targets", targets)


class MainWindow(QMainWindow):
    """Duo Sweeper 主窗口"""

    # ---- 主题名称常量 ----
    THEME_DARK = "暗夜橙影（默认）"
    THEME_LIGHT = "银盐月光"
    THEME_GREEN = "极光绿夜"

    # ---- 暗夜橙影 (Darkroom Orange) ----
    _QSS_DARK = """
    QWidget {
        background-color: #121212;
        color: #E0E0E0;
        font-family: -apple-system, "SF Pro Display", "Segoe UI", system-ui, sans-serif;
        font-size: 12px;
    }
    QMainWindow { background-color: #121212; }
    QGroupBox {
        border: none; border-top: 2px solid #FF8C00;
        margin-top: 12px; padding-top: 16px;
        font-weight: bold; color: #FF8C00; font-size: 13px;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
    QPushButton {
        background-color: #2C2C2C; color: #E0E0E0;
        border: 1px solid #3A3A3A; border-radius: 4px;
        padding: 6px 16px; min-width: 70px;
    }
    QPushButton:hover { background-color: #3E3E3E; border-color: #FF8C00; }
    QPushButton:pressed { background-color: #1E1E1E; }
    QPushButton:disabled { background-color: #1E1E1E; color: #666; border-color: #2A2A2A; }
    QPushButton#primaryBtn { background-color: #FF8C00; color: #121212; font-weight: bold; border: none; }
    QPushButton#primaryBtn:hover { background-color: #FFA726; }
    QPushButton#primaryBtn:pressed { background-color: #E67E00; }
    QPushButton#dangerBtn { background-color: #C62828; color: #FFF; font-weight: bold; border: none; }
    QPushButton#dangerBtn:hover { background-color: #E53935; }
    QPushButton#dangerBtn:pressed { background-color: #B71C1C; }
    QCheckBox { spacing: 8px; color: #E0E0E0; }
    QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #555; border-radius: 3px; background-color: #2C2C2C; }
    QCheckBox::indicator:checked { background-color: #FF8C00; border-color: #FF8C00; }
    QComboBox {
        background-color: #2C2C2C; border: 1px solid #3A3A3A;
        border-radius: 4px; padding: 4px 24px 4px 10px;
        min-width: 160px; color: #E0E0E0; font-size: 12px;
    }
    QComboBox:hover { border-color: #FF8C00; }
    QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left: 1px solid #3A3A3A; }
    QComboBox QAbstractItemView { background-color: #1E1E1E; border: 1px solid #3A3A3A; selection-background-color: #FF8C00; selection-color: #121212; color: #E0E0E0; }
    QLineEdit { background-color: #1E1E1E; border: 1px solid #3A3A3A; border-radius: 4px; padding: 4px 8px; color: #E0E0E0; }
    QLineEdit:focus { border-color: #FF8C00; }
    QListWidget { background-color: #1A1A1A; border: 1px solid #2A2A2A; border-radius: 4px; color: #E0E0E0; outline: none; }
    QListWidget::item { padding: 6px; border-bottom: 1px solid #222; }
    QListWidget::item:selected { background-color: #FF8C00; color: #121212; }
    QListWidget::item:hover:!selected { background-color: #252525; }
    QTextEdit, QPlainTextEdit { background-color: #1A1A1A; border: 1px solid #2A2A2A; border-radius: 4px; color: #E0E0E0; font-family: "SF Mono","Menlo","Consolas",monospace; font-size: 11px; }
    QScrollBar:vertical { background: #1A1A1A; width: 8px; border-radius: 4px; }
    QScrollBar::handle:vertical { background: #555; border-radius: 4px; min-height: 30px; }
    QScrollBar::handle:vertical:hover { background: #FF8C00; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QMenu { background-color: #1E1E1E; border: 1px solid #333; color: #E0E0E0; }
    QMenu::item:selected { background-color: #FF8C00; color: #121212; }
    QTabWidget::pane { border: 1px solid #333; background: #121212; }
    QTabBar::tab { background: #1E1E1E; color: #999; padding: 6px 16px; border-bottom: 2px solid transparent; }
    QTabBar::tab:selected { color: #FF8C00; border-bottom: 2px solid #FF8C00; }
    QTabBar::tab:hover:!selected { color: #CCC; }
    QToolTip { background-color: #2D2D2D; color: #E0E0E0; border: 1px solid #FF8C00; padding: 4px; }
    QStatusBar { background-color: #1A1A1A; color: #999; border-top: 1px solid #2A2A2A; }
    """

    # ---- 银盐月光 (Silver Gelatin) ----
    _QSS_LIGHT = """
    QWidget {
        background-color: #F5F5F0;
        color: #333333;
        font-family: -apple-system, "SF Pro Display", "Segoe UI", system-ui, sans-serif;
        font-size: 12px;
    }
    QMainWindow { background-color: #F5F5F0; }
    QGroupBox {
        border: none; border-top: 2px solid #546E7A;
        margin-top: 12px; padding-top: 16px;
        font-weight: bold; color: #546E7A; font-size: 13px;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; background-color: #F5F5F0; }
    QPushButton {
        background-color: #FFFFFF; color: #333333;
        border: 1px solid #C0C0C0; border-radius: 4px;
        padding: 6px 16px; min-width: 70px;
    }
    QPushButton:hover { background-color: #EBEBE5; border-color: #546E7A; }
    QPushButton:pressed { background-color: #D6D6CE; }
    QPushButton:disabled { background-color: #E8E8E2; color: #999; border-color: #D0D0D0; }
    QPushButton#primaryBtn { background-color: #546E7A; color: #FFF; font-weight: bold; border: none; }
    QPushButton#primaryBtn:hover { background-color: #5C7A88; }
    QPushButton#primaryBtn:pressed { background-color: #48626D; }
    QPushButton#dangerBtn { background-color: #BF616A; color: #FFF; font-weight: bold; border: none; }
    QPushButton#dangerBtn:hover { background-color: #CF737C; }
    QPushButton#dangerBtn:pressed { background-color: #A94E56; }
    QCheckBox { spacing: 8px; color: #333333; }
    QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #999; border-radius: 3px; background-color: #FFFFFF; }
    QCheckBox::indicator:checked { background-color: #546E7A; border-color: #546E7A; }
    QComboBox {
        background-color: #FFFFFF; border: 1px solid #C0C0C0;
        border-radius: 4px; padding: 4px 24px 4px 10px;
        min-width: 160px; color: #333333;
    }
    QComboBox:hover { border-color: #546E7A; }
    QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left: 1px solid #C0C0C0; }
    QComboBox QAbstractItemView { background-color: #FFF; border: 1px solid #C0C0C0; selection-background-color: #D6E0E8; selection-color: #333; color: #333; }
    QLineEdit { background-color: #FFF; border: 1px solid #C0C0C0; border-radius: 4px; padding: 4px 8px; color: #333; }
    QLineEdit:focus { border-color: #546E7A; }
    QListWidget { background-color: #FFF; border: 1px solid #D0D0D0; border-radius: 4px; color: #333; outline: none; }
    QListWidget::item { padding: 6px; border-bottom: 1px solid #E0E0DC; }
    QListWidget::item:selected { background-color: #D6E0E8; color: #333; }
    QListWidget::item:hover:!selected { background-color: #EDEDEA; }
    QTextEdit, QPlainTextEdit { background-color: #FFF; border: 1px solid #D0D0D0; border-radius: 4px; color: #333; font-family: "SF Mono","Menlo","Consolas",monospace; font-size: 11px; }
    QScrollBar:vertical { background: #EAEAE5; width: 8px; border-radius: 4px; }
    QScrollBar::handle:vertical { background: #B0B0B0; border-radius: 4px; min-height: 30px; }
    QScrollBar::handle:vertical:hover { background: #546E7A; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QMenu { background-color: #FFF; border: 1px solid #D0D0D0; color: #333; }
    QMenu::item:selected { background-color: #D6E0E8; color: #333; }
    QTabWidget::pane { border: 1px solid #D0D0D0; background: #F5F5F0; }
    QTabBar::tab { background: #EAEAE5; color: #666; padding: 6px 16px; border-bottom: 2px solid transparent; }
    QTabBar::tab:selected { color: #546E7A; border-bottom: 2px solid #546E7A; }
    QTabBar::tab:hover:!selected { color: #333; }
    QToolTip { background-color: #FFF; color: #333; border: 1px solid #546E7A; padding: 4px; }
    QStatusBar { background-color: #F0F0EB; color: #666; border-top: 1px solid #D0D0D0; }
    """

    # ---- 极光绿夜 (Aurora Green Night) ----
    _QSS_GREEN = """
    QWidget {
        background-color: #1B2A2E;
        color: #D4E7E2;
        font-family: -apple-system, "SF Pro Display", "Segoe UI", system-ui, sans-serif;
        font-size: 12px;
    }
    QMainWindow { background-color: #1B2A2E; }
    QGroupBox {
        border: none; border-top: 2px solid #2AFFBF;
        margin-top: 12px; padding-top: 16px;
        font-weight: bold; color: #2AFFBF; font-size: 13px;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; background-color: #1B2A2E; }
    QPushButton {
        background-color: #233439; color: #D4E7E2;
        border: 1px solid #2E4A4F; border-radius: 6px;
        padding: 6px 16px; min-width: 70px;
    }
    QPushButton:hover { background-color: #2A4046; border-color: #2AFFBF; }
    QPushButton:pressed { background-color: #1A2A2E; }
    QPushButton:disabled { background-color: #1A2A2E; color: #5A7A7A; border-color: #2E4A4F; }
    QPushButton#primaryBtn { background-color: #2AFFBF; color: #1B2A2E; font-weight: bold; border: none; }
    QPushButton#primaryBtn:hover { background-color: #5FFFD9; }
    QPushButton#primaryBtn:pressed { background-color: #1ACCA0; }
    QPushButton#dangerBtn { background-color: #FF6E6E; color: #1B2A2E; font-weight: bold; border: none; }
    QPushButton#dangerBtn:hover { background-color: #FF8C8C; }
    QPushButton#dangerBtn:pressed { background-color: #D94C4C; }
    QCheckBox { spacing: 8px; color: #D4E7E2; }
    QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #5A7A7A; border-radius: 3px; background-color: #233439; }
    QCheckBox::indicator:checked { background-color: #2AFFBF; border-color: #2AFFBF; }
    QComboBox {
        background-color: #233439; border: 1px solid #2E4A4F;
        border-radius: 6px; padding: 4px 24px 4px 10px;
        min-width: 160px; color: #D4E7E2;
    }
    QComboBox:hover { border-color: #2AFFBF; }
    QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left: 1px solid #2E4A4F; }
    QComboBox QAbstractItemView { background-color: #1E2F34; border: 1px solid #2E4A4F; selection-background-color: #2AFFBF; selection-color: #1B2A2E; color: #D4E7E2; }
    QLineEdit { background-color: #1E2F34; border: 1px solid #2E4A4F; border-radius: 6px; padding: 4px 8px; color: #D4E7E2; }
    QLineEdit:focus { border-color: #2AFFBF; }
    QListWidget { background-color: #17282B; border: 1px solid #2E4A4F; border-radius: 6px; color: #D4E7E2; outline: none; }
    QListWidget::item { padding: 6px; border-bottom: 1px solid #1E3034; }
    QListWidget::item:selected { background-color: #2AFFBF; color: #1B2A2E; }
    QListWidget::item:hover:!selected { background-color: #203539; }
    QTextEdit, QPlainTextEdit { background-color: #17282B; border: 1px solid #2E4A4F; border-radius: 6px; color: #D4E7E2; font-family: "SF Mono","JetBrains Mono","Consolas",monospace; font-size: 11px; }
    QScrollBar:vertical { background: #17282B; width: 8px; border-radius: 4px; }
    QScrollBar::handle:vertical { background: #3A5A5F; border-radius: 4px; min-height: 30px; }
    QScrollBar::handle:vertical:hover { background: #2AFFBF; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QMenu { background-color: #1E2F34; border: 1px solid #2E4A4F; color: #D4E7E2; }
    QMenu::item:selected { background-color: #2AFFBF; color: #1B2A2E; }
    QTabWidget::pane { border: 1px solid #2E4A4F; background: #1B2A2E; }
    QTabBar::tab { background: #1E2F34; color: #8BA4A0; padding: 6px 16px; border-bottom: 2px solid transparent; }
    QTabBar::tab:selected { color: #2AFFBF; border-bottom: 2px solid #2AFFBF; }
    QTabBar::tab:hover:!selected { color: #D4E7E2; }
    QToolTip { background-color: #1E2F34; color: #D4E7E2; border: 1px solid #2AFFBF; padding: 4px; }
    QStatusBar { background-color: #17282B; color: #8BA4A0; border-top: 1px solid #2E4A4F; }
    """

    # 主题映射
    THEMES: dict[str, str] = {
        THEME_DARK: _QSS_DARK,
        THEME_LIGHT: _QSS_LIGHT,
        THEME_GREEN: _QSS_GREEN,
    }

    def apply_theme(self, theme_name: str) -> None:
        """根据主题名称设置全局 QSS 样式"""
        qss = self.THEMES.get(theme_name, self._QSS_DARK)
        self.setStyleSheet(qss)
        self._current_theme = theme_name

        if hasattr(self, '_manual_dialog') and self._manual_dialog and self._manual_dialog.isVisible():
            self._manual_dialog.setStyleSheet(qss)

    def apply_language(self, lang: str) -> None:
        """切换界面语言并刷新所有控件文本"""
        self.lang = lang
        settings = QSettings("DuoSweeper", "DuoSweeper")
        settings.setValue("app_language", lang)
        self._refresh_ui_texts()

    def _refresh_ui_texts(self) -> None:
        """刷新所有控件的翻译文本"""
        L = self.lang
        # 窗口标题
        self.setWindowTitle(get_text("app_title", L))

        # 顶部按钮
        self.btn_select.setText(get_text("select_folder", L))
        if not self._folder_path:
            self.lbl_folder.setText(get_text("no_folder_selected", L))
        self.chk_watch.setText(get_text("enable_live_watch", L))

        # 同步目标
        self.grp_sync.setTitle(get_text("sync_target_folders", L))
        self.btn_add_sync.setText(get_text("add_sync_folder", L))
        self.btn_remove_sync.setText(get_text("remove_selected", L))

        # 监视方向/模式
        self.lbl_direction.setText(get_text("watch_direction", L))
        self.lbl_mode.setText(get_text("watch_mode", L))
        # 更新 QComboBox 显示文本（保留 data）
        for i in range(self.cmb_direction.count()):
            data = self.cmb_direction.itemData(i)
            key = {DIR_JPG_TO_RAW: "dir_jpg_to_raw", DIR_RAW_TO_JPG: "dir_raw_to_jpg", DIR_BOTH: "dir_both"}.get(data, "")
            if key:
                self.cmb_direction.setItemText(i, get_text(key, L))
        for i in range(self.cmb_mode.count()):
            data = self.cmb_mode.itemData(i)
            key = {MODE_ASK: "mode_ask", MODE_AUTO: "mode_auto", MODE_BATCH: "mode_batch"}.get(data, "")
            if key:
                self.cmb_mode.setItemText(i, get_text(key, L))

        # 扫描/清理按钮
        if self.btn_scan.isEnabled() or self.btn_scan.text() in ("开始扫描", "Start Scan"):
            self.btn_scan.setText(get_text("start_scan", L))
        self.btn_trash.setText(get_text("move_to_trash", L))
        self._update_collected_button()
        self.btn_settings.setText(get_text("settings", L))

        # 日志
        self.grp_log.setTitle(get_text("activity_log", L))
        self.chk_show_log.setText(get_text("show_activity_log", L))

        # 托盘菜单
        self._setup_tray_menu()

        # 重新填充方向/模式下拉框当前选中项的显示文本（保持 data 不变）
        self._update_collected_button()

    @staticmethod
    def _load_theme() -> str:
        """从 QSettings 加载已保存的主题名称"""
        settings = QSettings("DuoSweeper", "DuoSweeper")
        return settings.value("app_theme", MainWindow.THEME_DARK)

    @staticmethod
    def _save_theme(theme_name: str) -> None:
        """将主题名称保存到 QSettings"""
        settings = QSettings("DuoSweeper", "DuoSweeper")
        settings.setValue("app_theme", theme_name)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Duo Sweeper")
        self.setFixedSize(800, 600)

        # 加载并应用保存的语言
        settings = QSettings("DuoSweeper", "DuoSweeper")
        self.lang = settings.value("app_language", detect_system_language())

        # 加载并应用保存的主题
        saved_theme = self._load_theme()
        self.apply_theme(saved_theme)

        # ---- 系统托盘图标（用于后台通知 + 最小化到托盘） ----
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._create_tray_icon())
        self._tray.setToolTip("Duo Sweeper")
        self._setup_tray_menu()
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

        # ---- 实时监视器 ----
        self._watcher = FileWatcher(self)
        self._update_nam = QNetworkAccessManager(self)
        self._watcher.file_deleted.connect(self._on_file_deleted)

        # ---- 批量收集列表 ----
        self._collected_files: list[str] = []

        # 中央容器
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ---- 顶部：文件夹选择 + 实时监视开关 ----
        folder_row = QHBoxLayout()
        self.btn_select = QPushButton(get_text("select_folder", self.lang))
        self.btn_select.clicked.connect(self._select_folder)
        self.lbl_folder = QLabel(get_text("no_folder_selected", self.lang))
        self.chk_watch = QCheckBox(get_text("enable_live_watch", self.lang))
        self.chk_watch.toggled.connect(self._toggle_watcher)
        folder_row.addWidget(self.btn_select)
        folder_row.addWidget(self.lbl_folder, 1)
        folder_row.addWidget(self.chk_watch)
        layout.addLayout(folder_row)

        # ---- 同步目标文件夹管理区 ----
        self.sync_targets: list[dict] = load_sync_targets()

        self.grp_sync = QGroupBox(get_text("sync_target_folders", self.lang))
        sync_layout = QVBoxLayout(self.grp_sync)

        self.sync_list_widget = QListWidget()
        self.sync_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._refresh_sync_list()
        sync_layout.addWidget(self.sync_list_widget, 1)

        sync_btn_row = QHBoxLayout()
        self.btn_add_sync = QPushButton(get_text("add_sync_folder", self.lang))
        self.btn_add_sync.clicked.connect(self._add_sync_target)
        self.btn_remove_sync = QPushButton(get_text("remove_selected", self.lang))
        self.btn_remove_sync.clicked.connect(self._remove_sync_targets)
        sync_btn_row.addWidget(self.btn_add_sync)
        sync_btn_row.addWidget(self.btn_remove_sync)
        sync_btn_row.addStretch()
        sync_layout.addLayout(sync_btn_row)

        layout.addWidget(self.grp_sync)

        # ---- 第二行：监视方向 + 监视模式 ----
        mode_row = QHBoxLayout()
        self.lbl_direction = QLabel(get_text("watch_direction", self.lang))
        self.cmb_direction = QComboBox()
        self.cmb_direction.addItem(get_text("dir_jpg_to_raw", self.lang), DIR_JPG_TO_RAW)
        self.cmb_direction.addItem(get_text("dir_raw_to_jpg", self.lang), DIR_RAW_TO_JPG)
        self.cmb_direction.addItem(get_text("dir_both", self.lang), DIR_BOTH)
        self.cmb_direction.setEnabled(False)
        self.cmb_direction.currentTextChanged.connect(self._on_direction_changed)
        self.lbl_mode = QLabel(get_text("watch_mode", self.lang))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem(get_text("mode_ask", self.lang), MODE_ASK)
        self.cmb_mode.addItem(get_text("mode_auto", self.lang), MODE_AUTO)
        self.cmb_mode.addItem(get_text("mode_batch", self.lang), MODE_BATCH)
        self.cmb_mode.setEnabled(False)
        mode_row.addWidget(self.lbl_direction)
        mode_row.addWidget(self.cmb_direction)
        mode_row.addWidget(self.lbl_mode)
        mode_row.addWidget(self.cmb_mode)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # ---- 扫描按钮 ----
        self.btn_scan = QPushButton(get_text("start_scan", self.lang))
        self.btn_scan.setObjectName("primaryBtn")
        self.btn_scan.setEnabled(False)
        self.btn_scan.clicked.connect(self._start_scan)
        layout.addWidget(self.btn_scan)

        # ---- 结果列表（支持多选） ----
        self.result_list = QListWidget()
        self.result_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.result_list, 1)

        # ---- 底部按钮行：移至废纸篓 + 处理待清理文件 + 设置 ----
        bottom_row = QHBoxLayout()
        self.btn_trash = QPushButton(get_text("move_to_trash", self.lang))
        self.btn_trash.setObjectName("dangerBtn")
        self.btn_trash.setEnabled(False)
        self.btn_trash.clicked.connect(self._move_to_trash)
        self.btn_process_collected = QPushButton(f"{get_text('process_collected', self.lang)} (0)")
        self.btn_process_collected.setObjectName("primaryBtn")
        self.btn_process_collected.setEnabled(False)
        self.btn_process_collected.clicked.connect(self._show_batch_dialog)
        self.btn_settings = QPushButton(get_text("settings", self.lang))
        self.btn_settings.clicked.connect(self._show_settings_dialog)
        bottom_row.addWidget(self.btn_trash)
        bottom_row.addWidget(self.btn_process_collected)
        bottom_row.addStretch()
        bottom_row.addWidget(self.btn_settings)
        layout.addLayout(bottom_row)

        # ---- 操作日志（通过外部勾选框控制显示/隐藏） ----
        self.grp_log = QGroupBox(get_text("activity_log", self.lang))
        self.grp_log.setVisible(False)
        log_layout = QVBoxLayout(self.grp_log)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        btn_clear_log = QPushButton(get_text("clear_log", self.lang))
        btn_clear_log.clicked.connect(self.log_view.clear)
        log_layout.addWidget(btn_clear_log)

        self.chk_show_log = QCheckBox(get_text("show_activity_log", self.lang))
        self.chk_show_log.toggled.connect(self.grp_log.setVisible)

        layout.addWidget(self.chk_show_log)
        layout.addWidget(self.grp_log)

        # 内部状态
        self._folder_path: str | None = None

        # ---- 外置存储检测 ----
        self._known_root_paths: set[str] = set()   # 已知的卷根路径
        self._pending_volume: str | None = None     # 等待用户确认的新卷路径
        self._init_known_volumes()                  # 记录启动时已有的卷
        self._storage_timer = QTimer(self)
        self._storage_timer.timeout.connect(self._check_new_volumes)
        self._storage_timer.start(5000)             # 每 5 秒检测一次
        self._tray.messageClicked.connect(self._on_tray_message_clicked)

    # ---- 托盘相关 ----

    @staticmethod
    def _create_tray_icon() -> QIcon:
        """生成一个简单的托盘图标（蓝底白色 DS 字母），兼容 macOS/Windows"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(50, 120, 200))
        painter = QPainter(pixmap)
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPixelSize(36)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "DS")
        painter.end()
        return QIcon(pixmap)

    def _setup_tray_menu(self):
        """构建托盘右键菜单"""
        menu = self._tray.contextMenu() or self._tray.setContextMenu(None)
        from PySide6.QtWidgets import QMenu

        tray_menu = QMenu()

        action_show = QAction(get_text("tray_show_window", self.lang), self)
        action_show.triggered.connect(self._show_from_tray)
        tray_menu.addAction(action_show)

        tray_menu.addSeparator()

        action_quit = QAction(get_text("tray_quit", self.lang), self)
        action_quit.triggered.connect(self._quit_app)
        tray_menu.addAction(action_quit)

        self._tray.setContextMenu(tray_menu)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """托盘图标被双击时显示主窗口"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        """从托盘恢复显示主窗口"""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _quit_app(self):
        """从托盘菜单退出应用，停止监视器后退出"""
        self._watcher.stop()
        QApplication.quit()

    def closeEvent(self, event):
        """重写关闭事件：保存配置并隐藏到托盘而不退出应用"""
        # 保存同步目标配置
        save_sync_targets(self.sync_targets)
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "Duo Sweeper",
            get_text("tray_minimized", self.lang),
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    # ---- 外置存储检测 ----

    def _init_known_volumes(self):
        """记录启动时已挂载的所有卷，作为基准"""
        for info in QStorageInfo.mountedVolumes():
            if info.isValid() and info.isReady():
                self._known_root_paths.add(info.rootPath())

    def _check_new_volumes(self):
        """定时检测新挂载的存储卷"""
        import sys

        current_volumes = QStorageInfo.mountedVolumes()
        for info in current_volumes:
            if not info.isValid() or not info.isReady():
                continue
            root = info.rootPath()
            if root in self._known_root_paths:
                continue

            # 发现新卷，立即加入已知集合防止重复触发
            self._known_root_paths.add(root)

            # 过滤系统卷
            if self._is_system_volume(root):
                continue

            # 获取卷名：优先 displayName()，为空则回退到 rootPath()
            volume_name = info.displayName().strip() or root

            # 弹出托盘通知，询问用户
            self._pending_volume = root
            self._tray.showMessage(
                get_text("new_volume_title", self.lang),
                get_text("new_volume_msg", self.lang).format(name=volume_name),
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
            self._log_message(get_text("new_volume_log", self.lang).format(name=volume_name, path=root))

    @staticmethod
    def _is_system_volume(root_path: str) -> bool:
        """判断是否为系统卷（macOS/Windows），避免误添加

        macOS: "/"（根卷）、/System/Volumes/*、/Volumes/Macintosh HD*
        Windows: C:\（系统盘）
        """
        import sys

        if sys.platform == "darwin":
            # macOS 根卷 / 及其子系统卷
            if root_path == "/":
                return True
            system_prefixes = ("/System/Volumes", "/Volumes/Macintosh HD")
            return any(root_path.startswith(p) for p in system_prefixes)
        elif sys.platform == "win32":
            return root_path.lower().startswith("c:\\")
        return False

    def _on_tray_message_clicked(self):
        """用户点击托盘通知时，将新卷添加到监视"""
        if not self._pending_volume:
            return

        volume_root = self._pending_volume
        self._pending_volume = None

        # 优先选择 DCIM 目录（相机常用），否则使用卷根目录
        dcim_path = Path(volume_root) / "DCIM"
        target_path = str(dcim_path) if dcim_path.is_dir() else volume_root

        # 更新文件夹路径和界面
        self._folder_path = target_path
        self.lbl_folder.setText(target_path)
        self.btn_scan.setEnabled(True)

        # 自动启用实时监视
        if not self.chk_watch.isChecked():
            self.chk_watch.setChecked(True)
        else:
            exts = self._get_watched_extensions()
            self._watcher.stop()
            self._watcher.start(target_path, exts)

        self._log_message(get_text("watch_added_log", self.lang).format(path=target_path))
        self.statusBar().showMessage(get_text("watch_added", self.lang).format(path=target_path), 5000)

    # ---- 日志相关 ----

    def _log_message(self, message: str):
        """向操作日志追加一条带时间戳的记录，最多保留 50 条"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_view.append(f"{timestamp} {message}")
        # 超过 50 条时删除旧记录
        doc = self.log_view.document()
        while doc.blockCount() > 50:
            cursor = self.log_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # 删除多余换行

    # ---- 辅助方法 ----

    def _get_mode(self) -> str:
        """获取当前选中的监视模式（内部标识）"""
        return self.cmb_mode.currentData() or MODE_ASK

    def _get_direction(self) -> str:
        """获取当前选中的监视方向（内部标识）"""
        return self.cmb_direction.currentData() or DIR_BOTH

    def _get_watched_extensions(self) -> list[str]:
        """根据监视方向返回需要监视的文件后缀列表。

        JPG→RAW 方向：监视 JPG 文件。
        RAW→JPG 方向：监视 RAW 文件。
        双向：监视 JPG + RAW 文件。
        """
        direction = self._get_direction()
        if direction == DIR_JPG_TO_RAW:
            return list(JPG_SUFFIXES)
        elif direction == DIR_RAW_TO_JPG:
            return list(RAW_EXTENSIONS)
        else:  # DIR_BOTH
            return list(JPG_SUFFIXES | RAW_EXTENSIONS)

    def _restart_watcher(self):
        """用当前方向的后缀列表重启监视器（不停止 UI 状态）"""
        if self._folder_path and self.chk_watch.isChecked():
            self._watcher.stop()
            exts = self._get_watched_extensions()
            self._watcher.start(self._folder_path, exts)

    def _find_corresponding_files(self, deleted_path: Path) -> list[Path]:
        """根据被删除文件的后缀和监视方向，查找需要清理的对应文件。

        - 被删的是 JPG，方向为 JPG→RAW 或双向 → 查找同名 RAW
        - 被删的是 RAW，方向为 RAW→JPG 或双向 → 查找同名 JPG
        - 其他情况返回空列表
        """
        stem = deleted_path.stem.lower()
        folder = deleted_path.parent
        ext = deleted_path.suffix.lower()
        direction = self._get_direction()

        is_jpg = ext in JPG_SUFFIXES
        is_raw = ext in RAW_EXTENSIONS

        # 确定需要查找的目标后缀集合
        target_extensions: set[str] = set()
        if is_jpg and direction in (DIR_JPG_TO_RAW, DIR_BOTH):
            target_extensions = RAW_EXTENSIONS
        elif is_raw and direction in (DIR_RAW_TO_JPG, DIR_BOTH):
            target_extensions = JPG_SUFFIXES

        if not target_extensions:
            return []

        # 递归查找同主文件名的目标文件（含子文件夹）
        matched: list[Path] = []
        try:
            for p in folder.rglob("*"):
                if p.is_file() and p.stem.lower() == stem and p.suffix.lower() in target_extensions:
                    matched.append(p)
        except (PermissionError, OSError):
            pass

        return matched

    def _find_sync_files(self, deleted_path: Path) -> list[Path]:
        """在已启用的同步目标文件夹中递归搜索与被删除文件同主文件名的所有文件。

        返回去重后的文件路径列表（排除本地已处理的文件和被删文件自身）。
        若目标文件夹不可访问则跳过并记录日志。
        """
        stem = deleted_path.stem
        deleted_str = str(deleted_path)
        local_matched_strs: set[str] = set()

        # 收集本地已找到的对应文件路径，用于去重
        local_matched = self._find_corresponding_files(deleted_path)
        for p in local_matched:
            local_matched_strs.add(str(p))

        sync_files: list[Path] = []
        seen: set[str] = set()

        for target in self.sync_targets:
            if not target.get("enabled", True):
                continue
            target_dir = Path(target["path"])

            # 检查目录是否可访问（跳过不存在或无权限的目录）
            try:
                if not target_dir.is_dir():
                    continue
                target_dir.iterdir()
            except (PermissionError, OSError) as e:
                self._log_message(get_text("skip_inaccessible", self.lang).format(path=target_dir, error=e))
                continue

            # 递归搜索同主文件名的所有文件（含子文件夹，不限后缀）
            found_in_target: list[str] = []
            try:
                for p in target_dir.rglob(f"{stem}.*"):
                    if not p.is_file():
                        continue
                    p_str = str(p)
                    if p_str == deleted_str:
                        continue
                    if p_str in local_matched_strs:
                        continue
                    if p_str in seen:
                        continue
                    seen.add(p_str)
                    sync_files.append(p)
                    found_in_target.append(p.name)
            except (PermissionError, OSError) as e:
                self._log_message(get_text("read_sync_failed", self.lang).format(path=target_dir, error=e))
                continue

            # 记录该目标中找到的文件
            if found_in_target:
                self._log_message(
                    get_text("sync_found_files", self.lang).format(
                        path=target_dir, count=len(found_in_target), files=", ".join(found_in_target)
                    )
                )

        return sync_files

    # ---- 槽函数 ----

    def _select_folder(self):
        """弹出系统文件夹选择对话框，选中后更新路径标签"""
        path = QFileDialog.getExistingDirectory(self, get_text("select_folder", self.lang))
        if path:
            self._folder_path = path
            self.lbl_folder.setText(path)
            self.btn_scan.setEnabled(True)
            if self.chk_watch.isChecked():
                exts = self._get_watched_extensions()
                self._watcher.start(path, exts)

    def _toggle_watcher(self, checked: bool):
        """切换实时监视的开启/关闭"""
        if checked:
            if not self._folder_path:
                QMessageBox.warning(self, get_text("hint", self.lang), get_text("please_select_folder", self.lang))
                self.chk_watch.setChecked(False)
                return

            # 启动监视，禁用扫描相关按钮，启用方向/模式选择器
            exts = self._get_watched_extensions()
            self._watcher.start(self._folder_path, exts)
            self.btn_select.setEnabled(False)
            self.btn_scan.setEnabled(False)
            self.cmb_direction.setEnabled(True)
            self.cmb_mode.setEnabled(True)
            self.statusBar().showMessage(get_text("watch_started", self.lang), 3000)
        else:
            # 关闭监视前，若有待清理文件则询问用户
            if self._collected_files:
                count = len(self._collected_files)
                reply = QMessageBox.question(
                    self,
                    get_text("hint", self.lang),
                    get_text("discard_collected_confirm", self.lang).format(count=count),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    # 取消关闭，恢复复选框状态
                    self.chk_watch.setChecked(True)
                    return
                # 用户选择放弃，清空列表
                self._collected_files.clear()
                self._update_collected_button()

            # 停止监视，恢复按钮
            self._watcher.stop()
            self.btn_select.setEnabled(True)
            self.btn_scan.setEnabled(bool(self._folder_path))
            self.cmb_direction.setEnabled(False)
            self.cmb_mode.setEnabled(False)
            self.statusBar().showMessage(get_text("watch_stopped", self.lang), 3000)

    def _on_direction_changed(self, _text: str):
        """监视方向切换时，重启监视器以匹配新的后缀列表"""
        self._restart_watcher()

    def _on_file_deleted(self, file_path: str):
        """文件被删除时的回调：执行本地配对清理 + 跨文件夹同步清理"""
        deleted_file = Path(file_path)

        # ---- 第一步：本地配对清理 ----
        matched_files = self._find_corresponding_files(deleted_file)
        if matched_files:
            mode = self._get_mode()
            if mode == MODE_ASK:
                self._handle_mode_ask(matched_files, deleted_file)
            elif mode == MODE_AUTO:
                self._handle_mode_auto(matched_files)
            elif mode == MODE_BATCH:
                self._handle_mode_batch(matched_files)

        # ---- 第二步：跨文件夹同步清理（不限文件类型：JPG/RAW/XMP 等均触发） ----
        sync_files = self._find_sync_files(deleted_file)
        if sync_files:
            self._log_message(
                get_text("sync_search_summary", self.lang).format(
                    targets=len(self.sync_targets), count=len(sync_files)
                )
            )
            self._handle_sync_files(sync_files, deleted_file)
        else:
            self._log_message(get_text("sync_no_match", self.lang))

    def _handle_mode_ask(self, matched_files: list[Path], deleted_file: Path):
        """模式：每次询问 — 弹窗确认后清理"""
        deleted_name = deleted_file.name
        file_names = "\n".join(p.name for p in matched_files)
        reply = QMessageBox.question(
            self,
            get_text("file_deleted_title", self.lang),
            get_text("file_deleted_confirm", self.lang).format(name=deleted_name, files=file_names),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for p in matched_files:
                if QFile.moveToTrash(str(p)):
                    self.statusBar().showMessage(f"{get_text('cleaned', self.lang)} {p.name}", 5000)
                    self._log_message(f"{get_text('local_pair_clean', self.lang)} {p} {get_text('to_trash', self.lang)}")
                    self._tray.showMessage(
                        "Duo Sweeper",
                        f"{get_text('cleaned', self.lang)} {p.name}",
                        QSystemTrayIcon.MessageIcon.Information,
                        3000,
                    )
                else:
                    self.statusBar().showMessage(f"{get_text('clean_failed', self.lang)}: {p.name}", 5000)
                    self._log_message(f"{get_text('local_pair_clean', self.lang)}{get_text('clean_fail', self.lang)}: {p}")
                    QMessageBox.warning(
                        self,
                        get_text("clean_failed", self.lang),
                        get_text("trash_fail_msg", self.lang).format(name=p.name),
                    )

    def _handle_mode_auto(self, matched_files: list[Path]):
        """模式：自动清理 — 直接移入废纸篓并通知"""
        for p in matched_files:
            if QFile.moveToTrash(str(p)):
                self.statusBar().showMessage(f"{get_text('auto_cleaned', self.lang)}: {p.name}", 5000)
                self._log_message(f"{get_text('local_auto_clean', self.lang)} {p} {get_text('to_trash', self.lang)}")
                self._tray.showMessage(
                    "Duo Sweeper",
                    f"{get_text('auto_cleaned', self.lang)}: {p.name}",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
            else:
                self.statusBar().showMessage(f"{get_text('clean_failed', self.lang)}: {p.name}", 5000)
                self._log_message(f"{get_text('local_auto_clean', self.lang)}{get_text('clean_fail', self.lang)}: {p}")
                QMessageBox.warning(
                    self,
                    get_text("clean_failed", self.lang),
                    get_text("trash_fail_msg", self.lang).format(name=p.name),
                )

    def _handle_mode_batch(self, matched_files: list[Path]):
        """模式：批量收集 — 不弹窗不删除，仅记录路径"""
        for p in matched_files:
            path_str = str(p)
            if path_str not in self._collected_files:
                self._collected_files.append(path_str)
                self._log_message(f"{get_text('local_collect', self.lang)} {p}")
        self._update_collected_button()
        self.statusBar().showMessage(
            get_text("collected_count", self.lang).format(count=len(self._collected_files)), 3000
        )

    def _handle_sync_files(self, sync_files: list[Path], deleted_file: Path):
        """处理跨文件夹同步清理：根据当前模式操作同步目标中的匹配文件"""
        mode = self._get_mode()
        deleted_name = deleted_file.name
        file_names = "\n".join(str(p) for p in sync_files)

        if mode == MODE_ASK:
            reply = QMessageBox.question(
                self,
                get_text("sync_clean_title", self.lang),
                get_text("sync_delete_confirm", self.lang).format(name=deleted_name, files=file_names),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._trash_files(sync_files, label=get_text("sync_clean", self.lang))

        elif mode == MODE_AUTO:
            self._trash_files(sync_files, label=get_text("sync_auto_clean", self.lang))

        elif mode == MODE_BATCH:
            for p in sync_files:
                path_str = str(p)
                if path_str not in self._collected_files:
                    self._collected_files.append(path_str)
                    self._log_message(f"{get_text('sync_collect', self.lang)} {p}")
            self._update_collected_button()
            self.statusBar().showMessage(
                get_text("collected_count", self.lang).format(count=len(self._collected_files)), 3000
            )

    def _trash_files(self, files: list[Path], label: str = "清理"):
        """将文件列表移入废纸篓，记录成功/失败日志和通知。

        对于外部存储卷上的文件，若 moveToTrash 失败则提示用户存储可能不支持回收站，
        不会直接删除文件。
        """
        success = 0
        failed: list[Path] = []
        for p in files:
            if QFile.moveToTrash(str(p)):
                success += 1
                self._log_message(f"{label} {p} {get_text('to_trash', self.lang)}")
                self._tray.showMessage(
                    "Duo Sweeper",
                    f"{label}: {p.name}",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
            else:
                failed.append(p)
                self._log_message(f"{label}{get_text('clean_fail', self.lang)}: {p}")

        if failed:
            failed_names = "\n".join(str(p) for p in failed)
            QMessageBox.warning(
                self,
                get_text("clean_failed", self.lang),
                get_text("batch_clean_partial", self.lang).format(count=len(failed), files=failed_names),
            )

    def _update_collected_button(self):
        """更新"处理待清理文件"按钮的文本和启用状态"""
        count = len(self._collected_files)
        self.btn_process_collected.setText(f"{get_text('process_collected', self.lang)} ({count})")
        self.btn_process_collected.setEnabled(count > 0)

    def _show_batch_dialog(self):
        """弹出批量清理对话框，展示所有待清理文件"""
        if not self._collected_files:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(get_text("collected_files_title", self.lang))
        dialog.setMinimumSize(500, 400)
        dlg_layout = QVBoxLayout(dialog)

        lbl = QLabel(get_text("collected_files_prompt", self.lang).format(count=len(self._collected_files)))
        dlg_layout.addWidget(lbl)

        # 文件列表（多选，默认全选）
        list_widget = QListWidget()
        list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        list_widget.addItems(self._collected_files)
        for i in range(list_widget.count()):
            list_widget.item(i).setSelected(True)
        dlg_layout.addWidget(list_widget, 1)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_clean = QPushButton(get_text("clean_selected", self.lang))
        btn_cancel = QPushButton(get_text("cancel", self.lang))
        btn_row.addStretch()
        btn_row.addWidget(btn_clean)
        btn_row.addWidget(btn_cancel)
        dlg_layout.addLayout(btn_row)

        def do_clean():
            selected = list_widget.selectedItems()
            if not selected:
                QMessageBox.warning(dialog, get_text("hint", self.lang), get_text("please_select_files", self.lang))
                return

            success_count = 0
            failed_names: list[str] = []
            for item in selected:
                path_str = item.text()
                if QFile.moveToTrash(path_str):
                    success_count += 1
                    self._log_message(f"{get_text('batch_clean', self.lang)} {path_str} {get_text('to_trash', self.lang)}")
                    if path_str in self._collected_files:
                        self._collected_files.remove(path_str)
                else:
                    failed_names.append(Path(path_str).name)
                    self._log_message(f"{get_text('batch_clean', self.lang)}{get_text('clean_fail', self.lang)}: {path_str}")

            self._update_collected_button()

            msg = get_text("batch_clean_result", self.lang).format(count=success_count)
            if failed_names:
                msg += "\n" + get_text("batch_clean_partial", self.lang).format(count=len(failed_names), files="\n".join(failed_names))
            QMessageBox.information(dialog, get_text("clean_complete", self.lang), msg)
            dialog.accept()

        btn_clean.clicked.connect(do_clean)
        btn_cancel.clicked.connect(dialog.reject)

        dialog.exec()

    def _show_settings_dialog(self):
        """弹出设置对话框，包含主题、语言、RAW 后缀和元数据匹配"""
        # 防止重复打开
        if hasattr(self, '_settings_dialog') and self._settings_dialog and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        dialog = QDialog(self)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.Window)
        dialog.setWindowTitle(get_text("settings", self.lang))
        dialog.setMinimumSize(450, 420)
        dlg_layout = QVBoxLayout(dialog)

        # ---- 主题选择 ----
        theme_row = QHBoxLayout()
        lbl_theme = QLabel(get_text("theme_label", self.lang))
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(list(self.THEMES.keys()))
        saved_theme = self._load_theme()
        idx = self.cmb_theme.findText(saved_theme)
        if idx >= 0:
            self.cmb_theme.setCurrentIndex(idx)
        theme_row.addWidget(lbl_theme)
        theme_row.addWidget(self.cmb_theme, 1)
        theme_row.addStretch()
        dlg_layout.addLayout(theme_row)

        def on_theme_preview(name: str):
            self.apply_theme(name)

        self.cmb_theme.currentTextChanged.connect(on_theme_preview)

        # ---- 语言选择 ----
        lang_row = QHBoxLayout()
        lbl_lang = QLabel(get_text("language_label", self.lang))
        self.cmb_language = QComboBox()
        self.cmb_language.addItem(get_text("lang_zh", "zh"), "zh")
        self.cmb_language.addItem(get_text("lang_en", "en"), "en")
        lang_idx = self.cmb_language.findData(self.lang)
        if lang_idx >= 0:
            self.cmb_language.setCurrentIndex(lang_idx)
        lang_row.addWidget(lbl_lang)
        lang_row.addWidget(self.cmb_language, 1)
        lang_row.addStretch()
        dlg_layout.addLayout(lang_row)

        def on_lang_preview(_text: str):
            lang_code = self.cmb_language.currentData()
            if lang_code:
                self.apply_language(lang_code)

        self.cmb_language.currentTextChanged.connect(on_lang_preview)

        # ---- RAW 后缀编辑 ----
        lbl = QLabel(get_text("raw_ext_label", self.lang))
        dlg_layout.addWidget(lbl)

        editor = QPlainTextEdit()
        current_exts = "\n".join(sorted(RAW_EXTENSIONS))
        editor.setPlainText(current_exts)
        dlg_layout.addWidget(editor, 1)

        # 元数据匹配开关
        self.chk_metadata = QCheckBox(get_text("enable_metadata", self.lang))
        self.chk_metadata.setChecked(metadata_matching_enabled)
        dlg_layout.addWidget(self.chk_metadata)

        # ---- 关于分组 ----
        grp_about = QGroupBox(get_text("about_title", self.lang))
        about_layout = QVBoxLayout(grp_about)

        lbl_name = QLabel(get_text("app_title", self.lang))
        lbl_name.setStyleSheet("font-size: 16px; font-weight: bold;")
        lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(lbl_name)

        lbl_version = QLabel(f"{get_text('about_version', self.lang)}: 1.0.0")
        lbl_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(lbl_version)

        lbl_desc = QLabel(get_text("about_description", self.lang))
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(lbl_desc)

        lbl_dev = QLabel(get_text("about_developer", self.lang))
        lbl_dev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(lbl_dev)

        lbl_contact = QLabel(get_text("about_contact", self.lang))
        lbl_contact.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_contact.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(lbl_contact)

        lbl_license = QLabel(get_text("about_license", self.lang))
        lbl_license.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(lbl_license)

        btn_check_update = QPushButton(get_text("check_update", self.lang))
        btn_check_update.clicked.connect(self._check_for_updates)
        about_layout.addWidget(btn_check_update, alignment=Qt.AlignmentFlag.AlignCenter)

        dlg_layout.addWidget(grp_about)

        # ---- 用户手册按钮 ----
        btn_manual = QPushButton(get_text("manual_btn", self.lang))
        btn_manual.clicked.connect(self._show_manual_dialog)
        dlg_layout.addWidget(btn_manual)

        # ---- 底部按钮行 ----
        btn_row = QHBoxLayout()
        btn_save = QPushButton(get_text("save", self.lang))
        btn_restore = QPushButton(get_text("restore_default", self.lang))
        btn_cancel = QPushButton(get_text("cancel", self.lang))
        btn_row.addWidget(btn_restore)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        dlg_layout.addLayout(btn_row)

        def do_save():
            raw_text = editor.toPlainText()
            new_exts: set[str] = set()
            for line in raw_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if not line.startswith("."):
                    line = "." + line
                new_exts.add(line.lower())

            if not new_exts:
                QMessageBox.warning(dialog, get_text("hint", self.lang), get_text("ext_list_empty", self.lang))
                return

            set_raw_extensions(new_exts)
            set_metadata_matching(self.chk_metadata.isChecked())

            selected_theme = self.cmb_theme.currentText()
            self._save_theme(selected_theme)
            self.apply_theme(selected_theme)

            selected_lang = self.cmb_language.currentData()
            if selected_lang:
                self.apply_language(selected_lang)

            self._restart_watcher()

            QMessageBox.information(dialog, get_text("hint", self.lang), get_text("settings_saved", self.lang))
            dialog.close()   # ← 改为 close()，配合非模态窗口

        def do_restore():
            default_exts = get_default_raw_extensions()
            editor.setPlainText("\n".join(sorted(default_exts)))

        btn_save.clicked.connect(do_save)
        btn_restore.clicked.connect(do_restore)
        btn_cancel.clicked.connect(dialog.close)   # ← 改为 close()

        dialog.finished.connect(lambda: setattr(self, '_settings_dialog', None))
        dialog.show()   # ← 非模态显示，原来的 dialog.exec() 彻底删除
        self._settings_dialog = dialog
        
    # ---- 同步目标文件夹管理（主界面） ----

    def _refresh_sync_list(self):
        """将 self.sync_targets 同步到主界面列表控件（带复选框）"""
        self.sync_list_widget.clear()
        for target in self.sync_targets:
            item = QListWidgetItem(f"{target['path']}")
            item.setCheckState(
                Qt.CheckState.Checked if target.get("enabled", True) else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, target["path"])
            self.sync_list_widget.addItem(item)

    def _sync_list_to_config(self):
        """从主界面列表控件读取状态，回写到 self.sync_targets 并持久化"""
        new_targets: list[dict] = []
        for i in range(self.sync_list_widget.count()):
            item = self.sync_list_widget.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            enabled = item.checkState() == Qt.CheckState.Checked
            new_targets.append({"path": path, "enabled": enabled})
        self.sync_targets = new_targets
        save_sync_targets(self.sync_targets)

    def _add_sync_target(self):
        """添加一个同步目标文件夹"""
        path = QFileDialog.getExistingDirectory(self, get_text("add_sync_folder", self.lang))
        if not path:
            return

        # 检查是否已存在
        for t in self.sync_targets:
            if t["path"] == path:
                QMessageBox.information(self, get_text("hint", self.lang), get_text("folder_already_exists", self.lang))
                return

        self.sync_targets.append({"path": path, "enabled": True})
        save_sync_targets(self.sync_targets)
        self._refresh_sync_list()

    def _remove_sync_targets(self):
        """移除选中的同步目标文件夹"""
        selected = self.sync_list_widget.selectedItems()
        if not selected:
            QMessageBox.warning(self, get_text("hint", self.lang), get_text("please_select_folders", self.lang))
            return

        remove_paths: set[str] = set()
        for item in selected:
            remove_paths.add(item.data(Qt.ItemDataRole.UserRole))

        self.sync_targets = [t for t in self.sync_targets if t["path"] not in remove_paths]
        save_sync_targets(self.sync_targets)
        self._refresh_sync_list()

    def _show_manual_dialog(self):
        """弹出用户手册窗口（保存在主窗口上，便于主题同步）"""
        main_win = self.parent()
        if not main_win:
            main_win = self.window()
        if hasattr(main_win, '_manual_dialog') and main_win._manual_dialog and main_win._manual_dialog.isVisible():
            main_win._manual_dialog.raise_()
            main_win._manual_dialog.activateWindow()
            return

        dlg = ManualDialog(main_win, self.lang)
        dlg.show()
        main_win._manual_dialog = dlg
        dlg.raise_()
        dlg.activateWindow()

    def _check_for_updates(self):
        """异步检查 GitHub 上的最新版本并与本地版本比较"""
        url = QUrl("https://raw.githubusercontent.com/wqyxjia/duo_sweeper/main/version.txt")
        request = QNetworkRequest(url)

        reply = self._update_nam.get(request)
        reply.finished.connect(lambda r=reply: self._handle_update_reply(r))

    def _handle_update_reply(self, reply):
        """处理版本检查的 HTTP 响应"""
        from PySide6.QtGui import QDesktopServices

        if reply.error() != QNetworkReply.NetworkError.NoError:
            QMessageBox.information(
                self,
                get_text("update_title", self.lang),
                get_text("update_error", self.lang),
            )
            reply.deleteLater()
            return

        remote_version = bytes(reply.readAll()).decode("utf-8").strip()
        reply.deleteLater()

        # 获取本地版本号（从关于标签中提取，后备为 1.0.0）
        local_version = "1.0.0"
        if hasattr(self, '_settings_dialog') and self._settings_dialog:
            for lbl in self._settings_dialog.findChildren(QLabel):
                text = lbl.text()
                if text.startswith(get_text("about_version", self.lang) + ":"):
                    local_version = text.split(":", 1)[1].strip()
                    break

        # 简单的字符串比较（对数字版本号有效）
        if remote_version > local_version:
            result = QMessageBox.question(
                self,
                get_text("update_title", self.lang),
                get_text("update_found", self.lang).format(version=remote_version),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if result == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(
                    QUrl("https://github.com/wqyxjia/duo_sweeper/releases")
                )
        else:
            QMessageBox.information(
                self,
                get_text("update_title", self.lang),
                get_text("update_not_found", self.lang),
            )
    def _version_compare(v1: str, v2: str) -> int:
        """比较两个语义版本号，返回 1(v1>v2)、-1(v1<v2)、0(相等)"""
        parts1 = [int(p) for p in v1.split(".") if p.isdigit()]
        parts2 = [int(p) for p in v2.split(".") if p.isdigit()]
        for a, b in zip(parts1, parts2):
            if a > b:
                return 1
            if a < b:
                return -1
        if len(parts1) > len(parts2):
            return 1
        if len(parts1) < len(parts2):
            return -1
        return 0

    def _start_scan(self):
        """调用 scanner 模块扫描未匹配的 RAW 文件，结果填入列表"""
        if not self._folder_path:
            QMessageBox.warning(self, get_text("hint", self.lang), get_text("please_select_folder", self.lang))
            return

        self.result_list.clear()
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText(get_text("scanning", self.lang))

        try:
            unmatched_raws = find_unmatched_raw_files(
                self._folder_path, use_metadata=metadata_matching_enabled
            )
        except Exception as e:
            self.result_list.addItem(f"{get_text('scan_error', self.lang)}: {e}")
        else:
            if unmatched_raws:
                self.result_list.addItems(unmatched_raws)
                self.btn_trash.setEnabled(True)
                mode_desc = get_text("meta_match_desc", self.lang) if metadata_matching_enabled else ""
                self._log_message(get_text("scan_complete_found", self.lang).format(count=len(unmatched_raws), meta=mode_desc))
            else:
                self.result_list.addItem(get_text("no_unmatched_raw", self.lang))
                self.btn_trash.setEnabled(False)
                self._log_message(get_text("scan_complete_none", self.lang))
        finally:
            self.btn_scan.setText(get_text("start_scan", self.lang))
            self.btn_scan.setEnabled(True)

    def _move_to_trash(self):
        """将 QListWidget 中选中的文件移入系统废纸篓。

        对于外部存储卷上的文件，若 moveToTrash 失败则提示用户存储可能不支持回收站。
        """
        selected_items = self.result_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, get_text("hint", self.lang), get_text("please_select_files", self.lang))
            return

        success_count = 0
        failed_files: list[str] = []

        for item in selected_items:
            file_path = item.text()
            if QFile.moveToTrash(file_path):
                success_count += 1
                self._log_message(f"{get_text('manual_clean', self.lang)} {file_path} {get_text('to_trash', self.lang)}")
            else:
                failed_files.append(file_path)
                self._log_message(f"{get_text('manual_clean', self.lang)}{get_text('clean_fail', self.lang)}: {file_path}")

        for item in selected_items:
            if item.text() not in failed_files:
                self.result_list.takeItem(self.result_list.row(item))

        if self.result_list.count() == 0:
            self.result_list.addItem(get_text("no_unmatched_raw", self.lang))
            self.btn_trash.setEnabled(False)

        msg = get_text("trash_result_msg", self.lang).format(count=success_count)
        if failed_files:
            msg += "\n" + get_text("trash_partial_msg", self.lang).format(files="\n".join(failed_files))
        QMessageBox.information(self, get_text("clean_complete", self.lang), msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
