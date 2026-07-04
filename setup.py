"""
Duo Sweeper py2app 打包脚本
用法：python3 setup.py py2app
"""

from setuptools import setup

APP = ["main.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "packages": ["PySide6", "PIL"],
    "includes": ["scanner", "watcher", "i18n"],
    "excludes": [],
    "iconfile": None,  # 如果有 app_icon.icns，改为 "app_icon.icns"
    "plist": {
        "CFBundleDisplayName": "影伴 · Duo Sweeper",
        "CFBundleIdentifier": "com.duosweeper.app",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
}

setup(
    name="Duo Sweeper",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
