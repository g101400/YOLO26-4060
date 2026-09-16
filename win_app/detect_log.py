# -*- coding: utf-8 -*-
r"""检测记录落盘：公共「下载」目录，按天保留历史。

目录：Downloads\YOLOv5-Lite检测记录\detect_YYYYMMDD.csv
字段：时间,物体,置信度
编码：UTF-8 BOM（Excel 直接打开中文不乱码）；历史按天分文件，不自动清理。
"""
import glob
import os
import threading
from datetime import datetime

SUB_DIR = "YOLOv5-Lite检测记录"
HEADER = "时间,物体,置信度\n"


def downloads_dir():
    """取系统「下载」目录（兼容 OneDrive 重定向 / 非中文系统）。"""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD),
                        ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        FOLDERID_Downloads = GUID(0x374DE290, 0x123F, 0x4565,
                                  (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
        path_ptr = ctypes.c_wchar_p()
        res = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(FOLDERID_Downloads), 0, None, ctypes.byref(path_ptr))
        if res == 0 and path_ptr.value:
            value = path_ptr.value
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            return value
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


class DetectLog(object):
    def __init__(self, base_dir=None):
        self.dir = os.path.join(base_dir or downloads_dir(), SUB_DIR)
        try:
            os.makedirs(self.dir, exist_ok=True)
        except Exception:
            pass
        self._lock = threading.Lock()
        self._day = None
        self._path = None
        self._ensure_day()

    # ---------- 内部 ----------
    def _ensure_day(self):
        day = datetime.now().strftime("%Y%m%d")
        if day == self._day:
            return
        self._day = day
        self._path = os.path.join(self.dir, "detect_%s.csv" % day)
        if not os.path.isfile(self._path) or os.path.getsize(self._path) == 0:
            self._write("\ufeff" + HEADER, False)

    def _write(self, text, append):
        try:
            with open(self._path, "a" if append else "w", encoding="utf-8", newline="") as f:
                f.write(text)
            return True
        except Exception:
            return False

    # ---------- 对外 ----------
    @property
    def path(self):
        self._ensure_day()
        return self._path

    @property
    def location(self):
        return self.dir

    def append(self, name, prob, ts=None):
        """写入一条：时间,物体,置信度"""
        with self._lock:
            self._ensure_day()
            ts = ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return self._write("%s,%s,%.2f\n" % (ts, name, prob), True)

    def rows_today(self):
        with self._lock:
            self._ensure_day()
            return self._count(self._path)

    @staticmethod
    def _count(path):
        try:
            with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                n = sum(1 for line in f if line.strip())
            return max(0, n - 1)          # 去掉表头
        except Exception:
            return 0

    def history(self):
        """[(日期, 条数), ...]，按日期倒序"""
        items = []
        for p in sorted(glob.glob(os.path.join(self.dir, "detect_*.csv")), reverse=True):
            name = os.path.basename(p)
            day = name[len("detect_"):-len(".csv")]
            if len(day) == 8:
                day = "%s-%s-%s" % (day[:4], day[4:6], day[6:])
            items.append((day, self._count(p)))
        return items

    def clear_today(self):
        with self._lock:
            self._ensure_day()
            return self._write("\ufeff" + HEADER, False)

    def clear_all(self):
        with self._lock:
            n = 0
            for p in glob.glob(os.path.join(self.dir, "detect_*.csv")):
                try:
                    os.remove(p)
                    n += 1
                except Exception:
                    pass
            self._day = None
            self._ensure_day()
            return n
