from pathlib import Path

from PySide6.QtCore import QObject, QFileSystemWatcher, QTimer, Signal


class FileWatcher(QObject):
    """监视指定文件夹（含子文件夹），当匹配后缀的文件被移除时发出 file_deleted(str) 信号。

    提供两种监视机制：
      1. QFileSystemWatcher — 实时监听所有子文件夹变化（系统级通知）。
      2. 定时快照对比 — 每 5 秒扫描一次，与上次快照对比找出丢失的文件。
    两种机制并行运行，互补覆盖不同场景。
    """

    # 信号：携带被删除文件的完整路径
    file_deleted = Signal(str)

    # 定时快照扫描间隔（毫秒）
    _SNAPSHOT_INTERVAL_MS = 5000

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # ---- 文件夹监听器 ----
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)

        # ---- 定时快照对比 ----
        self._timer = QTimer(self)
        self._timer.setInterval(self._SNAPSHOT_INTERVAL_MS)
        self._timer.timeout.connect(self._snapshot_check)

        # 内部状态
        self._folder: Path | None = None           # 当前监视的根文件夹
        self._extensions: set[str] = set()         # 监视的后缀集合（小写）
        self._snapshot: set[str] = set()           # 上一次快照：完整路径集合
        self._watched_dirs: set[str] = set()       # 当前被 QFileSystemWatcher 监听的目录

    # ---- 公开方法 ----

    def start(self, folder_path: str, extensions: list[str]) -> None:
        """启动监视指定文件夹（含所有子文件夹）。

        Args:
            folder_path: 要监视的文件夹路径。
            extensions: 要监视的文件后缀列表，如 ['.jpg', '.jpeg'] 或 ['.CR3', '.NEF']。
        """
        folder = Path(folder_path)
        if not folder.is_dir():
            raise FileNotFoundError(f"目录不存在: {folder_path}")

        self.stop()

        self._folder = folder
        self._extensions = {ext.lower() for ext in extensions}

        # 递归添加所有子文件夹到监视
        self._add_dirs_recursive(folder)

        # 记录初始快照（完整路径）
        self._snapshot = self._scan_all_matched()

        # 启动定时快照对比
        self._timer.start()

    def stop(self) -> None:
        """停止所有监视。"""
        self._timer.stop()
        # 移除所有被监视的目录
        if self._watched_dirs:
            self._watcher.removePaths(list(self._watched_dirs))
        self._folder = None
        self._extensions.clear()
        self._snapshot.clear()
        self._watched_dirs.clear()

    # ---- 内部方法 ----

    def _add_dirs_recursive(self, root: Path) -> None:
        """递归将 root 及所有子文件夹添加到 QFileSystemWatcher。"""
        dirs_to_add: list[str] = []
        try:
            for p in root.rglob("*"):
                if p.is_dir():
                    dir_str = str(p)
                    if dir_str not in self._watched_dirs:
                        dirs_to_add.append(dir_str)
        except (PermissionError, OSError):
            pass

        # 根目录本身也要加入
        root_str = str(root)
        if root_str not in self._watched_dirs:
            dirs_to_add.insert(0, root_str)

        if dirs_to_add:
            self._watcher.addPaths(dirs_to_add)
            self._watched_dirs.update(dirs_to_add)

    def _scan_all_matched(self) -> set[str]:
        """递归扫描所有被监视目录，返回匹配后缀的文件完整路径集合。"""
        if not self._folder:
            return set()
        result: set[str] = set()
        try:
            for p in self._folder.rglob("*"):
                if p.is_file() and p.suffix.lower() in self._extensions:
                    result.add(str(p))
        except (PermissionError, OSError):
            pass
        return result

    def _on_directory_changed(self, path: str) -> None:
        """QFileSystemWatcher 触发的目录变化回调。

        对比快照找出被移除的文件，同时检查是否有新子文件夹需要监视。
        """
        # 检查是否有新子文件夹需要添加监视
        try:
            dir_path = Path(path)
            for p in dir_path.iterdir():
                if p.is_dir():
                    dir_str = str(p)
                    if dir_str not in self._watched_dirs:
                        self._watcher.addPath(dir_str)
                        self._watched_dirs.add(dir_str)
        except (PermissionError, OSError):
            pass

        # 对比快照找出被删除的文件
        current = self._scan_all_matched()
        removed = self._snapshot - current

        for full_path in removed:
            self.file_deleted.emit(full_path)

        # 更新快照
        self._snapshot = current

    def _snapshot_check(self) -> None:
        """定时快照对比，作为 QFileSystemWatcher 的补充机制。

        某些系统或场景下文件系统事件可能丢失，
        定时扫描可以兜底捕获变化。
        同时刷新目录结构以捕获新建的子文件夹。
        """
        if not self._folder:
            return

        # 刷新目录结构：检测新子文件夹并添加监视
        try:
            for p in self._folder.rglob("*"):
                if p.is_dir():
                    dir_str = str(p)
                    if dir_str not in self._watched_dirs:
                        self._watcher.addPath(dir_str)
                        self._watched_dirs.add(dir_str)
        except (PermissionError, OSError):
            pass

        # 对比快照找出被删除的文件
        current = self._scan_all_matched()
        removed = self._snapshot - current

        for full_path in removed:
            self.file_deleted.emit(full_path)

        # 更新快照
        self._snapshot = current
