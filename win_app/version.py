# -*- coding: utf-8 -*-
"""版本信息（Windows 端单一事实来源）。

版本规划（2026-09-16 定）：
    1.2.1 – 1.9.8  → YOLOv5-Lite 系列
    2.0.1 – 2.9.8  → YOLOv8 系列
    3.0.1 – 3.9.8  → YOLO11 系列
    6.0.1 – 6.9.8  → YOLO26 系列
    （4.x / 5.x 预留未启用）
Android 端的版本以 app/src/main/AndroidManifest.xml 的 versionName 为准，
两端发版时需保持同一版本号。
"""
APP_NAME = "YOLOv5-Lite 实时检测"
APP_VERSION = "1.2.1"
PLATFORM = "Windows"


# 主版本号前缀 → 系列名（4.x / 5.x 预留未启用）
SERIES_TABLE = (
    ("1.", "YOLOv5-Lite 系列"),
    ("2.", "YOLOv8 系列"),
    ("3.", "YOLO11 系列"),
    ("6.", "YOLO26 系列"),
)


def series(version=None):
    """按主版本号判定所属系列。"""
    v = version or APP_VERSION
    for prefix, name in SERIES_TABLE:
        if v.startswith(prefix):
            return name
    return "未知系列"


if __name__ == "__main__":
    print("%s %s (%s) - %s" % (APP_NAME, APP_VERSION, PLATFORM, series()))
