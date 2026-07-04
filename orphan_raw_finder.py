from pathlib import Path

# 支持的 RAW 文件后缀（小写，带点号）
RAW_EXTENSIONS = {".cr3", ".nef", ".arw", ".dng", ".orf"}

# 支持的 JPG 文件后缀（小写，带点号）
JPG_EXTENSIONS = {".jpg", ".jpeg"}


def find_orphan_raw_files(folder: str) -> list[str]:
    """扫描指定文件夹，返回找不到对应 JPG 的 RAW 文件完整路径列表。

    逻辑：
      1. 收集所有 JPG 文件的主文件名（不含后缀，不区分大小写）。
      2. 遍历所有 RAW 文件，若其主文件名不在 JPG 集合中，则视为"孤儿"。
    """
    folder_path = Path(folder)
    if not folder_path.is_dir():
        raise FileNotFoundError(f"目录不存在: {folder}")

    # 1. 建立 JPG 主文件名集合（统一小写以实现不区分大小写匹配）
    jpg_stems: set[str] = set()
    for p in folder_path.iterdir():
        if p.is_file() and p.suffix.lower() in JPG_EXTENSIONS:
            jpg_stems.add(p.stem.lower())

    # 2. 收集所有 RAW 文件，筛选出没有对应 JPG 的孤儿
    orphans: list[str] = []
    for p in folder_path.iterdir():
        if p.is_file() and p.suffix.lower() in RAW_EXTENSIONS:
            if p.stem.lower() not in jpg_stems:
                orphans.append(str(p))

    return orphans


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    results = find_orphan_raw_files(target)
    if results:
        print(f"发现 {len(results)} 个孤儿 RAW 文件：")
        for r in results:
            print(f"  {r}")
    else:
        print("未发现孤儿 RAW 文件。")
