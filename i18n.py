"""Duo Sweeper 国际化模块"""

import locale


def detect_system_language() -> str:
    """检测系统语言：以 zh 开头返回 'zh'，否则返回 'en'"""
    try:
        lang_code = locale.getdefaultlocale()[0] or ""
        return "zh" if lang_code.startswith("zh") else "en"
    except Exception:
        return "en"


def get_text(key: str, lang: str = "zh") -> str:
    """根据 key 和语言返回翻译文本，找不到时返回 key 本身"""
    entry = STR.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("en", key))


STR: dict[str, dict[str, str]] = {
    # ---- 应用标题 ----
    "app_title": {"zh": "影伴 · Duo Sweeper", "en": "Duo Sweeper"},
    "app_tray_tooltip": {"zh": "Duo Sweeper", "en": "Duo Sweeper"},

    # ---- 主窗口按钮 ----
    "select_folder": {"zh": "选择文件夹", "en": "Select Folder"},
    "no_folder_selected": {"zh": "未选择文件夹", "en": "No folder selected"},
    "enable_live_watch": {"zh": "启用实时监视", "en": "Enable Live Watch"},
    "start_scan": {"zh": "开始扫描", "en": "Start Scan"},
    "scanning": {"zh": "扫描中...", "en": "Scanning..."},
    "move_to_trash": {"zh": "移至废纸篓", "en": "Move to Trash"},
    "process_collected": {"zh": "处理待清理文件", "en": "Process Collected"},
    "settings": {"zh": "设置", "en": "Settings"},

    # ---- 同步目标文件夹 ----
    "sync_target_folders": {"zh": "同步目标文件夹", "en": "Sync Target Folders"},
    "add_sync_folder": {"zh": "添加同步文件夹", "en": "Add Sync Folder"},
    "remove_selected": {"zh": "移除选中", "en": "Remove Selected"},

    # ---- 监视方向 ----
    "watch_direction": {"zh": "监视方向：", "en": "Watch Direction:"},
    "dir_jpg_to_raw": {"zh": "JPG 删除 → 清理 RAW", "en": "JPG Deleted → Clean RAW"},
    "dir_raw_to_jpg": {"zh": "RAW 删除 → 清理 JPG", "en": "RAW Deleted → Clean JPG"},
    "dir_both": {"zh": "双向", "en": "Bidirectional"},

    # ---- 监视模式 ----
    "watch_mode": {"zh": "监视模式：", "en": "Watch Mode:"},
    "mode_ask": {"zh": "每次询问", "en": "Ask Each Time"},
    "mode_auto": {"zh": "自动清理", "en": "Auto Clean"},
    "mode_batch": {"zh": "批量收集", "en": "Batch Collect"},

    # ---- 操作日志 ----
    "activity_log": {"zh": "操作日志", "en": "Activity Log"},
    "show_activity_log": {"zh": "显示操作日志", "en": "Show Activity Log"},
    "clear_log": {"zh": "清空日志", "en": "Clear Log"},

    # ---- 设置对话框 ----
    "theme_label": {"zh": "界面主题：", "en": "Theme:"},
    "language_label": {"zh": "语言：", "en": "Language:"},
    "lang_zh": {"zh": "中文", "en": "Chinese"},
    "lang_en": {"zh": "English", "en": "English"},
    "raw_ext_label": {"zh": "RAW 文件后缀列表（每行一个，带点号，如 .CR3）：", "en": "RAW file extensions (one per line, with dot, e.g. .CR3):"},
    "enable_metadata": {"zh": "启用元数据匹配（基于 EXIF 拍摄时间 + 相机序列号）", "en": "Enable metadata matching (EXIF DateTimeOriginal + CameraSerialNumber)"},
    "save": {"zh": "保存", "en": "Save"},
    "restore_default": {"zh": "恢复默认", "en": "Restore Default"},
    "cancel": {"zh": "取消", "en": "Cancel"},

    # ---- 批量清理对话框 ----
    "collected_files_title": {"zh": "待清理文件", "en": "Files to Process"},
    "collected_files_prompt": {"zh": "共 {count} 个文件，请选择要清理的项目：", "en": "{count} files found. Select items to clean:"},
    "clean_selected": {"zh": "清理选中", "en": "Clean Selected"},

    # ---- 提示消息 ----
    "hint": {"zh": "提示", "en": "Hint"},
    "please_select_folder": {"zh": "请先选择文件夹", "en": "Please select a folder first"},
    "please_select_files": {"zh": "请先选中要清理的文件", "en": "Please select files to clean"},
    "please_select_folders": {"zh": "请先选中要移除的文件夹", "en": "Please select folders to remove"},
    "folder_already_exists": {"zh": "该文件夹已在列表中", "en": "This folder is already in the list"},
    "ext_list_empty": {"zh": "后缀列表不能为空", "en": "Extension list cannot be empty"},
    "settings_saved": {"zh": "设置已保存", "en": "Settings saved"},

    # ---- 确认对话框 ----
    "discard_collected_confirm": {"zh": "还有 {count} 个待清理文件，是否放弃？", "en": "{count} files pending. Discard them?"},
    "file_deleted_confirm": {"zh": "检测到 {name} 被删除，是否同步清理对应文件？\n\n{files}", "en": "{name} was deleted. Clean corresponding files?\n\n{files}"},
    "sync_delete_confirm": {"zh": "检测到 {name} 被删除，以下同步目标中的文件也将被清理？\n\n{files}", "en": "{name} was deleted. Also clean these sync target files?\n\n{files}"},

    # ---- 对话框标题 ----
    "file_deleted_title": {"zh": "检测到文件被删除", "en": "File Deletion Detected"},
    "sync_clean_title": {"zh": "跨文件夹同步清理", "en": "Cross-Folder Sync Clean"},

    # ---- 清理结果 ----
    "cleaned": {"zh": "已清理", "en": "Cleaned"},
    "auto_cleaned": {"zh": "已自动清理", "en": "Auto cleaned"},
    "clean_failed": {"zh": "清理失败", "en": "Cleanup Failed"},
    "trash_fail_msg": {"zh": "无法将 {name} 移入废纸篓。\n文件可能已被永久删除或存储设备不支持回收站。", "en": "Cannot move {name} to trash.\nThe file may have been permanently deleted or the storage does not support a recycle bin."},
    "batch_clean_result": {"zh": "已清理 {count} 个文件", "en": "{count} files cleaned"},
    "batch_clean_partial": {"zh": "失败 {count} 个：\n{files}\n\n无法移入废纸篓，文件可能已被永久删除或存储设备不支持回收站。", "en": "{count} failed:\n{files}\n\nCannot move to trash. Files may be permanently deleted or storage doesn't support recycle bin."},
    "clean_complete": {"zh": "清理完成", "en": "Cleanup Complete"},
    "trash_result_msg": {"zh": "已清理 {count} 个文件，已放入废纸篓", "en": "{count} files moved to trash"},
    "trash_partial_msg": {"zh": "以下文件清理失败：\n{files}\n\n无法移入废纸篓，文件可能已被永久删除或存储设备不支持回收站。", "en": "Failed to clean:\n{files}\n\nCannot move to trash. Files may be permanently deleted or storage doesn't support recycle bin."},

    # ---- 状态栏 ----
    "watch_started": {"zh": "实时监视已启动", "en": "Live watch started"},
    "watch_stopped": {"zh": "实时监视已停止", "en": "Live watch stopped"},
    "watch_added": {"zh": "已添加监视: {path}", "en": "Watching: {path}"},
    "collected_count": {"zh": "已收集 {count} 个待清理文件", "en": "{count} files collected for cleanup"},

    # ---- 扫描结果 ----
    "scan_error": {"zh": "扫描出错", "en": "Scan error"},
    "no_unmatched_raw": {"zh": "未发现需要清理的 RAW 文件", "en": "No unmatched RAW files found"},
    "scan_complete_found": {"zh": "扫描完成：发现 {count} 个未匹配 RAW {meta}", "en": "Scan complete: {count} unmatched RAW files found {meta}"},
    "scan_complete_none": {"zh": "扫描完成：未发现未匹配 RAW 文件", "en": "Scan complete: no unmatched RAW files"},
    "meta_match_desc": {"zh": "（含元数据匹配）", "en": "(with metadata matching)"},

    # ---- 托盘 ----
    "tray_show_window": {"zh": "显示主窗口", "en": "Show Window"},
    "tray_quit": {"zh": "退出", "en": "Quit"},
    "tray_minimized": {"zh": "已最小化到托盘，双击图标可恢复窗口", "en": "Minimized to tray. Double-click to restore."},

    # ---- 外置存储 ----
    "new_volume_title": {"zh": "检测到新存储卷", "en": "New Storage Detected"},
    "new_volume_msg": {"zh": "卷 '{name}' 已挂载，点击此处添加监视", "en": "Volume '{name}' mounted. Click to add watch."},
    "new_volume_log": {"zh": "检测到新存储卷: {name} ({path})", "en": "New volume: {name} ({path})"},
    "watch_added_log": {"zh": "已添加监视: {path}", "en": "Watching: {path}"},

    # ---- 跳过不可访问目录 ----
    "skip_inaccessible": {"zh": "跳过不可访问的同步目标: {path} ({error})", "en": "Skipping inaccessible sync target: {path} ({error})"},
    "read_sync_failed": {"zh": "读取同步目标失败: {path} ({error})", "en": "Failed to read sync target: {path} ({error})"},

    # ---- 同步文件查找日志 ----
    "sync_found_files": {"zh": "同步目标 {path} 中找到 {count} 个同名文件: {files}", "en": "Sync target {path}: found {count} matching files: {files}"},
    "sync_search_summary": {"zh": "跨文件夹同步: 从 {targets} 个目标中找到 {count} 个同名文件待处理", "en": "Cross-folder sync: {count} matching files found across {targets} targets"},
    "sync_no_match": {"zh": "跨文件夹同步: 未在同步目标中找到同名文件", "en": "Cross-folder sync: no matching files in sync targets"},

    # ---- 本地清理日志 ----
    "local_pair_clean": {"zh": "本地配对清理", "en": "Local pair clean"},
    "local_auto_clean": {"zh": "本地自动清理", "en": "Local auto clean"},
    "local_collect": {"zh": "本地收集", "en": "Local collect"},
    "sync_clean": {"zh": "同步清理", "en": "Sync clean"},
    "sync_auto_clean": {"zh": "同步自动清理", "en": "Sync auto clean"},
    "sync_collect": {"zh": "同步收集", "en": "Sync collect"},
    "manual_clean": {"zh": "手动清理", "en": "Manual clean"},
    "batch_clean": {"zh": "批量清理", "en": "Batch clean"},
    "to_trash": {"zh": "→ 废纸篓", "en": "→ Trash"},
    "clean_fail": {"zh": "清理失败", "en": "Clean failed"},

    # ---- 关于对话框 ----
    "about_title": {"zh": "关于 Duo Sweeper", "en": "About Duo Sweeper"},
    "about_version": {"zh": "版本", "en": "Version"},
    "about_description": {"zh": "双格式照片智能清理工具", "en": "Smart dual-format photo cleaner"},
    "about_developer": {"zh": "开发者：QYWang", "en": "Developer: QYWang"},
    "about_contact": {"zh": "联系方式：dearairrose@outlook.com", "en": "Contact: dearairrose@outlook.com"},
    "about_license": {"zh": "MIT 许可证", "en": "MIT License"},
    "check_update": {"zh": "检查更新", "en": "Check for Updates"},
    "checking_update": {"zh": "正在检查...", "en": "Checking..."},
    "update_found": {"zh": "发现新版本 {version}，是否前往下载？", "en": "New version {version} found. Open download page?"},
    "update_not_found": {"zh": "已经是最新版本", "en": "Already up to date"},
    "update_error": {"zh": "无法检查更新", "en": "Failed to check for updates"},
    "update_title": {"zh": "检查更新", "en": "Check for Updates"},

    # ---- 用户手册 ----
    "manual_btn": {"zh": "用户手册", "en": "User Manual"},
    "manual_title": {"zh": "用户手册", "en": "User Manual"},
    "close_btn": {"zh": "关闭", "en": "Close"},
    "manual_content": {
        "zh": """
影伴 · Duo Sweeper 用户手册

概述
影伴是一款专为摄影爱好者设计的双格式照片清理工具。
当你删除 JPG 或 RAW 文件时，它会自动帮你清理对应的另一种格式，
避免手动查找的麻烦，节省存储空间。

主要功能
• 实时监视 – 监视选中的文件夹，感知文件删除并联动清理
• 手动扫描 – 一键扫描文件夹内失去配对的 RAW 或 JPG 文件
• 双向清理 – 删除 JPG 可清理 RAW，删除 RAW 亦可清理 JPG
• 跨文件夹同步 – 将清理操作同步到其他文件夹或存储卡
• 元数据匹配 – 当文件名不一致时，通过拍摄信息智能配对
• 操作日志 – 记录每一次清理操作，可随时查看
• 多主题 – 提供暗夜橙影、银盐月光、极光绿夜三种视觉风格
• 多语言 – 支持中文和英文，可跟随系统或手动切换

使用步骤
1. 启动应用，选择要监视的照片文件夹。
2. 在"同步目标文件夹"中添加需要同步清理的其他文件夹。
3. 勾选"启用实时监视"，选择监视模式和方向。
4. 正常浏览与删除照片（在访达或其它看图软件中操作）。
5. 应用将自动或按你设定的方式帮你清理配对文件。
6. 定期打开"处理待清理文件"按钮，确认批量清理。

安全说明
• 所有被清理的文件均会移入系统废纸篓，你可以随时放回。
• 本应用不会直接永久删除你的任何文件。
• 首次使用建议先用测试文件夹熟悉流程。

联系与反馈
开发者：QYWang
邮箱：dearairrose@outlook.com
""",
        "en": """
Duo Sweeper User Manual

Overview
Duo Sweeper is a smart dual-format photo cleaner designed for photographers.
When you delete a JPG or RAW file, it automatically removes the corresponding
paired format, saving you from manual searching and freeing up storage.

Key Features
• Live Watch – Monitor a folder and react to file deletions in real time
• Manual Scan – Find orphaned RAW/JPG files in a folder with one click
• Bidirectional Cleaning – Deleting a JPG removes its RAW, and vice versa
• Cross-folder Sync – Mirror cleanup actions to backup folders or memory cards
• Metadata Matching – Match files by EXIF data when filenames differ
• Activity Log – Keep track of every cleaning operation
• Multiple Themes – Choose from Darkroom Orange, Silver Gelatin, and Aurora Forest
• Multilingual – Supports Chinese and English, auto-detected or manual

How to Use
1. Launch the app and select a photo folder to watch.
2. Add sync target folders under "Sync Target Folders".
3. Enable "Live Watch" and choose your preferred mode and direction.
4. Browse and delete photos normally (in Finder or any image viewer).
5. The app will clean paired files automatically or according to your preference.
6. Periodically review and confirm batch cleanup via "Process Collected Files".

Safety Notes
• All cleaned files are moved to the system Trash, fully recoverable.
• This app never permanently deletes any file directly.
• If using for the first time, test with a sample folder to get comfortable.

Contact & Feedback
Developer: QYWang
Email: dearairrose@outlook.com
"""
    },
}
