import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QFile, QSettings, QStorageInfo, QTimer, Qt
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

# 监视模式常量
MODE_ASK = "每次询问"
MODE_AUTO = "自动清理"
MODE_BATCH = "批量收集"

# 监视方向常量
DIR_JPG_TO_RAW = "JPG 删除 → 清理 RAW"
DIR_RAW_TO_JPG = "RAW 删除 → 清理 JPG"
DIR_BOTH = "双向"

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

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Duo Sweeper")
        self.setFixedSize(800, 600)

        # ---- 系统托盘图标（用于后台通知 + 最小化到托盘） ----
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._create_tray_icon())
        self._tray.setToolTip("Duo Sweeper")
        self._setup_tray_menu()
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

        # ---- 实时监视器 ----
        self._watcher = FileWatcher(self)
        self._watcher.file_deleted.connect(self._on_file_deleted)

        # ---- 批量收集列表 ----
        self._collected_files: list[str] = []

        # 中央容器
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ---- 顶部：文件夹选择 + 实时监视开关 ----
        folder_row = QHBoxLayout()
        self.btn_select = QPushButton("选择文件夹")
        self.btn_select.clicked.connect(self._select_folder)
        self.lbl_folder = QLabel("未选择文件夹")
        self.lbl_folder.setStyleSheet("color: gray;")
        self.chk_watch = QCheckBox("启用实时监视")
        self.chk_watch.toggled.connect(self._toggle_watcher)
        folder_row.addWidget(self.btn_select)
        folder_row.addWidget(self.lbl_folder, 1)
        folder_row.addWidget(self.chk_watch)
        layout.addLayout(folder_row)

        # ---- 同步目标文件夹管理区 ----
        self.sync_targets: list[dict] = load_sync_targets()

        self.grp_sync = QGroupBox("同步目标文件夹")
        sync_layout = QVBoxLayout(self.grp_sync)

        self.sync_list_widget = QListWidget()
        self.sync_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._refresh_sync_list()
        sync_layout.addWidget(self.sync_list_widget, 1)

        sync_btn_row = QHBoxLayout()
        self.btn_add_sync = QPushButton("添加同步文件夹")
        self.btn_add_sync.clicked.connect(self._add_sync_target)
        self.btn_remove_sync = QPushButton("移除选中")
        self.btn_remove_sync.clicked.connect(self._remove_sync_targets)
        sync_btn_row.addWidget(self.btn_add_sync)
        sync_btn_row.addWidget(self.btn_remove_sync)
        sync_btn_row.addStretch()
        sync_layout.addLayout(sync_btn_row)

        layout.addWidget(self.grp_sync)

        # ---- 第二行：监视方向 + 监视模式 ----
        mode_row = QHBoxLayout()
        self.lbl_direction = QLabel("监视方向：")
        self.cmb_direction = QComboBox()
        self.cmb_direction.addItems([DIR_JPG_TO_RAW, DIR_RAW_TO_JPG, DIR_BOTH])
        self.cmb_direction.setEnabled(False)
        self.cmb_direction.currentTextChanged.connect(self._on_direction_changed)
        self.lbl_mode = QLabel("监视模式：")
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems([MODE_ASK, MODE_AUTO, MODE_BATCH])
        self.cmb_mode.setEnabled(False)
        mode_row.addWidget(self.lbl_direction)
        mode_row.addWidget(self.cmb_direction)
        mode_row.addWidget(self.lbl_mode)
        mode_row.addWidget(self.cmb_mode)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # ---- 扫描按钮 ----
        self.btn_scan = QPushButton("开始扫描")
        self.btn_scan.setEnabled(False)
        self.btn_scan.clicked.connect(self._start_scan)
        layout.addWidget(self.btn_scan)

        # ---- 结果列表（支持多选） ----
        self.result_list = QListWidget()
        self.result_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.result_list, 1)

        # ---- 底部按钮行：移至废纸篓 + 处理待清理文件 + 设置 ----
        bottom_row = QHBoxLayout()
        self.btn_trash = QPushButton("移至废纸篓")
        self.btn_trash.setEnabled(False)
        self.btn_trash.clicked.connect(self._move_to_trash)
        self.btn_process_collected = QPushButton("处理待清理文件 (0)")
        self.btn_process_collected.setEnabled(False)
        self.btn_process_collected.clicked.connect(self._show_batch_dialog)
        self.btn_settings = QPushButton("设置")
        self.btn_settings.clicked.connect(self._show_settings_dialog)
        bottom_row.addWidget(self.btn_trash)
        bottom_row.addWidget(self.btn_process_collected)
        bottom_row.addStretch()
        bottom_row.addWidget(self.btn_settings)
        layout.addLayout(bottom_row)

        # ---- 操作日志（通过外部勾选框控制显示/隐藏） ----
        self.grp_log = QGroupBox("操作日志")
        self.grp_log.setVisible(False)
        log_layout = QVBoxLayout(self.grp_log)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.clicked.connect(self.log_view.clear)
        log_layout.addWidget(btn_clear_log)

        self.chk_show_log = QCheckBox("显示操作日志")
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

        action_show = QAction("显示主窗口", self)
        action_show.triggered.connect(self._show_from_tray)
        tray_menu.addAction(action_show)

        tray_menu.addSeparator()

        action_quit = QAction("退出", self)
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
            "已最小化到托盘，双击图标可恢复窗口",
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
                "检测到新存储卷",
                f"卷 '{volume_name}' 已挂载，点击此处添加监视",
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
            self._log_message(f"检测到新存储卷: {volume_name} ({root})")

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
        self.lbl_folder.setStyleSheet("color: black;")
        self.btn_scan.setEnabled(True)

        # 自动启用实时监视
        if not self.chk_watch.isChecked():
            self.chk_watch.setChecked(True)
        else:
            exts = self._get_watched_extensions()
            self._watcher.stop()
            self._watcher.start(target_path, exts)

        self._log_message(f"已添加监视: {target_path}")
        self.statusBar().showMessage(f"已添加监视: {target_path}", 5000)

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
        """获取当前选中的监视模式"""
        return self.cmb_mode.currentText()

    def _get_direction(self) -> str:
        """获取当前选中的监视方向"""
        return self.cmb_direction.currentText()

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
                self._log_message(f"跳过不可访问的同步目标: {target_dir} ({e})")
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
                self._log_message(f"读取同步目标失败: {target_dir} ({e})")
                continue

            # 记录该目标中找到的文件
            if found_in_target:
                self._log_message(
                    f"同步目标 {target_dir} 中找到 {len(found_in_target)} 个同名文件: "
                    + ", ".join(found_in_target)
                )

        return sync_files

    # ---- 槽函数 ----

    def _select_folder(self):
        """弹出系统文件夹选择对话框，选中后更新路径标签"""
        path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if path:
            self._folder_path = path
            self.lbl_folder.setText(path)
            self.lbl_folder.setStyleSheet("color: black;")
            self.btn_scan.setEnabled(True)

            # 若已勾选实时监视，自动启动
            if self.chk_watch.isChecked():
                exts = self._get_watched_extensions()
                self._watcher.start(path, exts)

    def _toggle_watcher(self, checked: bool):
        """切换实时监视的开启/关闭"""
        if checked:
            if not self._folder_path:
                QMessageBox.warning(self, "提示", "请先选择文件夹")
                self.chk_watch.setChecked(False)
                return

            # 启动监视，禁用扫描相关按钮，启用方向/模式选择器
            exts = self._get_watched_extensions()
            self._watcher.start(self._folder_path, exts)
            self.btn_select.setEnabled(False)
            self.btn_scan.setEnabled(False)
            self.cmb_direction.setEnabled(True)
            self.cmb_mode.setEnabled(True)
            self.statusBar().showMessage("实时监视已启动", 3000)
        else:
            # 关闭监视前，若有待清理文件则询问用户
            if self._collected_files:
                count = len(self._collected_files)
                reply = QMessageBox.question(
                    self,
                    "提示",
                    f"还有 {count} 个待清理文件，是否放弃？",
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
            self.statusBar().showMessage("实时监视已停止", 3000)

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
                f"跨文件夹同步: 从 {len(self.sync_targets)} 个目标中找到 "
                f"{len(sync_files)} 个同名文件待处理"
            )
            self._handle_sync_files(sync_files, deleted_file)
        else:
            self._log_message(f"跨文件夹同步: 未在同步目标中找到同名文件")

    def _handle_mode_ask(self, matched_files: list[Path], deleted_file: Path):
        """模式：每次询问 — 弹窗确认后清理"""
        deleted_name = deleted_file.name
        file_names = "\n".join(p.name for p in matched_files)
        reply = QMessageBox.question(
            self,
            "检测到文件被删除",
            f"检测到 {deleted_name} 被删除，是否同步清理对应文件？\n\n{file_names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for p in matched_files:
                if QFile.moveToTrash(str(p)):
                    self.statusBar().showMessage(f"已清理 {p.name}", 5000)
                    self._log_message(f"本地配对清理 {p} → 废纸篓")
                    self._tray.showMessage(
                        "Duo Sweeper",
                        f"已清理 {p.name}",
                        QSystemTrayIcon.MessageIcon.Information,
                        3000,
                    )
                else:
                    self.statusBar().showMessage(f"清理失败: {p.name}", 5000)
                    self._log_message(f"本地配对清理失败: {p}")
                    QMessageBox.warning(
                        self,
                        "清理失败",
                        f"无法将 {p.name} 移入废纸篓。\n"
                        "文件可能已被永久删除或存储设备不支持回收站。",
                    )

    def _handle_mode_auto(self, matched_files: list[Path]):
        """模式：自动清理 — 直接移入废纸篓并通知"""
        for p in matched_files:
            if QFile.moveToTrash(str(p)):
                self.statusBar().showMessage(f"已自动清理: {p.name}", 5000)
                self._log_message(f"本地自动清理 {p} → 废纸篓")
                self._tray.showMessage(
                    "Duo Sweeper",
                    f"已自动清理: {p.name}",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
            else:
                self.statusBar().showMessage(f"清理失败: {p.name}", 5000)
                self._log_message(f"本地自动清理失败: {p}")
                QMessageBox.warning(
                    self,
                    "清理失败",
                    f"无法将 {p.name} 移入废纸篓。\n"
                    "文件可能已被永久删除或存储设备不支持回收站。",
                )

    def _handle_mode_batch(self, matched_files: list[Path]):
        """模式：批量收集 — 不弹窗不删除，仅记录路径"""
        for p in matched_files:
            path_str = str(p)
            if path_str not in self._collected_files:
                self._collected_files.append(path_str)
                self._log_message(f"本地收集 {p}")
        self._update_collected_button()
        self.statusBar().showMessage(
            f"已收集 {len(self._collected_files)} 个待清理文件", 3000
        )

    def _handle_sync_files(self, sync_files: list[Path], deleted_file: Path):
        """处理跨文件夹同步清理：根据当前模式操作同步目标中的匹配文件"""
        mode = self._get_mode()
        deleted_name = deleted_file.name
        file_names = "\n".join(str(p) for p in sync_files)

        if mode == MODE_ASK:
            reply = QMessageBox.question(
                self,
                "跨文件夹同步清理",
                f"检测到 {deleted_name} 被删除，以下同步目标中的文件也将被清理？\n\n{file_names}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._trash_files(sync_files, label="同步清理")

        elif mode == MODE_AUTO:
            self._trash_files(sync_files, label="同步自动清理")

        elif mode == MODE_BATCH:
            for p in sync_files:
                path_str = str(p)
                if path_str not in self._collected_files:
                    self._collected_files.append(path_str)
                    self._log_message(f"同步收集 {p}")
            self._update_collected_button()
            self.statusBar().showMessage(
                f"已收集 {len(self._collected_files)} 个待清理文件", 3000
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
                self._log_message(f"{label} {p} → 废纸篓")
                self._tray.showMessage(
                    "Duo Sweeper",
                    f"{label}: {p.name}",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
            else:
                failed.append(p)
                self._log_message(f"{label}失败: {p}")

        if failed:
            failed_names = "\n".join(str(p) for p in failed)
            QMessageBox.warning(
                self,
                "部分清理失败",
                f"成功 {success} 个，失败 {len(failed)} 个：\n{failed_names}\n\n"
                "无法移入废纸篓，文件可能已被永久删除或存储设备不支持回收站。",
            )

    def _update_collected_button(self):
        """更新"处理待清理文件"按钮的文本和启用状态"""
        count = len(self._collected_files)
        self.btn_process_collected.setText(f"处理待清理文件 ({count})")
        self.btn_process_collected.setEnabled(count > 0)

    def _show_batch_dialog(self):
        """弹出批量清理对话框，展示所有待清理文件"""
        if not self._collected_files:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("待清理文件")
        dialog.setMinimumSize(500, 400)
        dlg_layout = QVBoxLayout(dialog)

        lbl = QLabel(f"共 {len(self._collected_files)} 个文件，请选择要清理的项目：")
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
        btn_clean = QPushButton("清理选中")
        btn_cancel = QPushButton("取消")
        btn_row.addStretch()
        btn_row.addWidget(btn_clean)
        btn_row.addWidget(btn_cancel)
        dlg_layout.addLayout(btn_row)

        def do_clean():
            selected = list_widget.selectedItems()
            if not selected:
                QMessageBox.warning(dialog, "提示", "请先选中要清理的文件")
                return

            success_count = 0
            failed_names: list[str] = []
            for item in selected:
                path_str = item.text()
                if QFile.moveToTrash(path_str):
                    success_count += 1
                    self._log_message(f"批量清理 {path_str} → 废纸篓")
                    if path_str in self._collected_files:
                        self._collected_files.remove(path_str)
                else:
                    failed_names.append(Path(path_str).name)
                    self._log_message(f"批量清理失败: {path_str}")

            self._update_collected_button()

            msg = f"已清理 {success_count} 个文件"
            if failed_names:
                msg += (
                    f"\n失败 {len(failed_names)} 个：\n" + "\n".join(failed_names)
                    + "\n\n无法移入废纸篓，文件可能已被永久删除或存储设备不支持回收站。"
                )
            QMessageBox.information(dialog, "清理完成", msg)
            dialog.accept()

        btn_clean.clicked.connect(do_clean)
        btn_cancel.clicked.connect(dialog.reject)

        dialog.exec()

    def _show_settings_dialog(self):
        """弹出设置对话框，包含 RAW 后缀和元数据匹配"""
        dialog = QDialog(self)
        dialog.setWindowTitle("设置")
        dialog.setMinimumSize(450, 320)
        dlg_layout = QVBoxLayout(dialog)

        # ---- RAW 后缀编辑 ----
        lbl = QLabel("RAW 文件后缀列表（每行一个，带点号，如 .CR3）：")
        dlg_layout.addWidget(lbl)

        editor = QPlainTextEdit()
        current_exts = "\n".join(sorted(RAW_EXTENSIONS))
        editor.setPlainText(current_exts)
        dlg_layout.addWidget(editor, 1)

        # 元数据匹配开关
        self.chk_metadata = QCheckBox("启用元数据匹配（基于 EXIF 拍摄时间 + 相机序列号）")
        self.chk_metadata.setChecked(metadata_matching_enabled)
        dlg_layout.addWidget(self.chk_metadata)

        # ---- 底部按钮行 ----
        btn_row = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_restore = QPushButton("恢复默认")
        btn_cancel = QPushButton("取消")
        btn_row.addWidget(btn_restore)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        dlg_layout.addLayout(btn_row)

        def do_save():
            """保存所有设置"""
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
                QMessageBox.warning(dialog, "提示", "后缀列表不能为空")
                return

            set_raw_extensions(new_exts)
            set_metadata_matching(self.chk_metadata.isChecked())

            # 如果监视器正在运行，用新后缀重启
            self._restart_watcher()

            QMessageBox.information(dialog, "提示", "设置已保存")
            dialog.accept()

        def do_restore():
            """恢复默认后缀列表"""
            default_exts = get_default_raw_extensions()
            editor.setPlainText("\n".join(sorted(default_exts)))

        btn_save.clicked.connect(do_save)
        btn_restore.clicked.connect(do_restore)
        btn_cancel.clicked.connect(dialog.reject)

        dialog.exec()

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
        path = QFileDialog.getExistingDirectory(self, "选择同步目标文件夹")
        if not path:
            return

        # 检查是否已存在
        for t in self.sync_targets:
            if t["path"] == path:
                QMessageBox.information(self, "提示", "该文件夹已在列表中")
                return

        self.sync_targets.append({"path": path, "enabled": True})
        save_sync_targets(self.sync_targets)
        self._refresh_sync_list()

    def _remove_sync_targets(self):
        """移除选中的同步目标文件夹"""
        selected = self.sync_list_widget.selectedItems()
        if not selected:
            QMessageBox.warning(self, "提示", "请先选中要移除的文件夹")
            return

        remove_paths: set[str] = set()
        for item in selected:
            remove_paths.add(item.data(Qt.ItemDataRole.UserRole))

        self.sync_targets = [t for t in self.sync_targets if t["path"] not in remove_paths]
        save_sync_targets(self.sync_targets)
        self._refresh_sync_list()

    def _start_scan(self):
        """调用 scanner 模块扫描未匹配的 RAW 文件，结果填入列表"""
        if not self._folder_path:
            QMessageBox.warning(self, "提示", "请先选择文件夹")
            return

        self.result_list.clear()
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("扫描中...")

        try:
            unmatched_raws = find_unmatched_raw_files(
                self._folder_path, use_metadata=metadata_matching_enabled
            )
        except Exception as e:
            self.result_list.addItem(f"扫描出错: {e}")
        else:
            if unmatched_raws:
                self.result_list.addItems(unmatched_raws)
                self.btn_trash.setEnabled(True)
                mode_desc = "（含元数据匹配）" if metadata_matching_enabled else ""
                self._log_message(f"扫描完成：发现 {len(unmatched_raws)} 个未匹配 RAW {mode_desc}")
            else:
                self.result_list.addItem("未发现需要清理的 RAW 文件")
                self.btn_trash.setEnabled(False)
                self._log_message("扫描完成：未发现未匹配 RAW 文件")
        finally:
            self.btn_scan.setText("开始扫描")
            self.btn_scan.setEnabled(True)

    def _move_to_trash(self):
        """将 QListWidget 中选中的文件移入系统废纸篓。

        对于外部存储卷上的文件，若 moveToTrash 失败则提示用户存储可能不支持回收站。
        """
        selected_items = self.result_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请先选中要清理的文件")
            return

        success_count = 0
        failed_files: list[str] = []

        for item in selected_items:
            file_path = item.text()
            if QFile.moveToTrash(file_path):
                success_count += 1
                self._log_message(f"手动清理 {file_path} → 废纸篓")
            else:
                failed_files.append(file_path)
                self._log_message(f"手动清理失败: {file_path}")

        for item in selected_items:
            if item.text() not in failed_files:
                self.result_list.takeItem(self.result_list.row(item))

        if self.result_list.count() == 0:
            self.result_list.addItem("未发现需要清理的 RAW 文件")
            self.btn_trash.setEnabled(False)

        msg = f"已清理 {success_count} 个文件，已放入废纸篓"
        if failed_files:
            msg += (
                "\n以下文件清理失败：\n" + "\n".join(failed_files)
                + "\n\n无法移入废纸篓，文件可能已被永久删除或存储设备不支持回收站。"
            )
        QMessageBox.information(self, "清理完成", msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
