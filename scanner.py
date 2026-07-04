from pathlib import Path

# 默认 RAW 后缀列表
_DEFAULT_RAW_EXTENSIONS = {".cr3", ".nef", ".arw", ".dng", ".orf", ".raf", ".rw2", ".pef", ".srw"}

# 当前生效的 RAW 后缀集合（可被 set_raw_extensions 修改）
RAW_EXTENSIONS: set[str] = set(_DEFAULT_RAW_EXTENSIONS)

JPG_EXTENSIONS = {".jpg", ".jpeg"}

# 元数据匹配开关（默认开启）
metadata_matching_enabled = True

# 尝试导入 Pillow，用于 EXIF 元数据读取
try:
    from PIL import Image
    from PIL.ExifTags import Tag
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def set_raw_extensions(exts: set[str]) -> None:
    """更新全局 RAW 后缀集合，实时影响扫描和监视逻辑。"""
    RAW_EXTENSIONS.clear()
    RAW_EXTENSIONS.update(exts)


def get_default_raw_extensions() -> set[str]:
    """返回默认的 RAW 后缀集合（用于恢复默认设置）。"""
    return set(_DEFAULT_RAW_EXTENSIONS)


def set_metadata_matching(enabled: bool) -> None:
    """开启或关闭元数据匹配功能。"""
    global metadata_matching_enabled
    metadata_matching_enabled = enabled


def _read_exif_tags(file_path: Path) -> dict[str, str]:
    """读取图像文件的 EXIF 信息，返回关键标签的字符串值。

    尝试读取的标签：
      - DateTimeOriginal（拍摄时间）
      - CameraSerialNumber（相机序列号）
      - LensSerialNumber（镜头序列号，备用）
    """
    if not _HAS_PIL:
        return {}

    try:
        with Image.open(file_path) as img:
            exif_data = img.getexif()
            if not exif_data:
                return {}
    except Exception:
        return {}

    # EXIF tag ID 常量（避免硬编码字符串）
    TAG_DATETIME_ORIGINAL = 36867      # 0x9003
    TAG_CAMERA_SERIAL = 42033          # 0xA431
    TAG_LENS_SERIAL = 42036            # 0xA434

    result: dict[str, str] = {}
    for tag_id, value in exif_data.items():
        if tag_id == TAG_DATETIME_ORIGINAL and isinstance(value, str):
            result["DateTimeOriginal"] = value
        elif tag_id == TAG_CAMERA_SERIAL and isinstance(value, str):
            result["CameraSerialNumber"] = value
        elif tag_id == TAG_LENS_SERIAL and isinstance(value, str):
            result["LensSerialNumber"] = value

    return result


def _metadata_match_key(tags: dict[str, str]) -> str | None:
    """根据 EXIF 标签生成匹配键。

    优先使用 DateTimeOriginal + CameraSerialNumber 组合；
    若缺少任一字段，返回 None 表示无法匹配。
    """
    dto = tags.get("DateTimeOriginal", "")
    serial = tags.get("CameraSerialNumber", "")
    if dto and serial:
        return f"{dto}|{serial}"
    return None


def find_unmatched_raw_files(folder: str, use_metadata: bool = False) -> list[str]:
    """扫描指定文件夹，返回找不到对应 JPG 的 RAW 文件完整路径列表。

    逻辑：
      1. 基于文件名匹配（主文件名相同）。
      2. 若启用元数据匹配，对文件名未匹配的 RAW 文件，尝试通过
         EXIF DateTimeOriginal + CameraSerialNumber 与 JPG 配对。
      3. 仍无法匹配的 RAW 文件列为"未匹配"。
    """
    folder_path = Path(folder)
    if not folder_path.is_dir():
        raise FileNotFoundError(f"目录不存在: {folder}")

    # 1. 基于文件名建立 JPG 主文件名集合
    jpg_stems: set[str] = set()
    for p in folder_path.iterdir():
        if p.is_file() and p.suffix.lower() in JPG_EXTENSIONS:
            jpg_stems.add(p.stem.lower())

    # 2. 筛选文件名未匹配的 RAW 文件
    unmatched_raws: list[str] = []
    filename_unmatched_raws: list[Path] = []
    for p in folder_path.iterdir():
        if p.is_file() and p.suffix.lower() in RAW_EXTENSIONS:
            if p.stem.lower() not in jpg_stems:
                filename_unmatched_raws.append(p)

    # 3. 元数据匹配（可选后备逻辑）
    if use_metadata and _HAS_PIL and filename_unmatched_raws:
        # 收集所有 JPG 的元数据匹配键
        jpg_metadata_keys: set[str] = set()
        jpg_files: list[Path] = []
        for p in folder_path.iterdir():
            if p.is_file() and p.suffix.lower() in JPG_EXTENSIONS:
                jpg_files.append(p)

        for jpg_path in jpg_files:
            tags = _read_exif_tags(jpg_path)
            key = _metadata_match_key(tags)
            if key:
                jpg_metadata_keys.add(key)

        # 对未匹配的 RAW 尝试元数据匹配
        for raw_path in filename_unmatched_raws:
            tags = _read_exif_tags(raw_path)
            key = _metadata_match_key(tags)
            if key and key in jpg_metadata_keys:
                continue  # 元数据匹配成功，跳过此 RAW（不列为未匹配）
            unmatched_raws.append(str(raw_path))
    else:
        unmatched_raws = [str(p) for p in filename_unmatched_raws]

    return unmatched_raws


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    results = find_unmatched_raw_files(target)
    if results:
        print(f"发现 {len(results)} 个需要清理的 RAW 文件：")
        for r in results:
            print(f"  {r}")
    else:
        print("未发现需要清理的 RAW 文件。")
