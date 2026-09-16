# -*- coding: utf-8 -*-
"""YOLOv5-Lite 实时检测 —— Windows 桌面版（Tkinter + ncnn + OpenCV）。

与安卓端 v1.2.1 对齐的能力：
    摄像头实时检测、中文标签、状态栏（几个物体 / 分别是什么 / FPS）、
    检测结果自动存盘（公共「下载」目录，按天保留历史）、帮助 / 关于菜单（含版本号）。

自检模式（无需摄像头，用于打包后验证）：
    python app.py --selftest
"""
import os
import queue
import sys
import threading
import time
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import tkinter as tk
from tkinter import messagebox, ttk

import coco_cn
import version
from detector import Detector, MODELS, DEFAULT_MODEL_INDEX
from detect_log import DetectLog

THRESHOLDS = (("标准 0.60", 0.60), ("均衡 0.45", 0.45), ("灵敏 0.35", 0.35), ("极敏 0.25", 0.25))
BG = "#111827"
PANEL = "#1F2937"
FG = "#FFFFFF"
SUB = "#9CA3AF"
ACCENT = "#38BDF8"


def resource_dir():
    """模型目录：优先 exe 同级 models/（便于换模型），其次打包进 exe 的 models/。"""
    base = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    external = os.path.join(base, "models")
    if os.path.isdir(external):
        return external
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = os.path.join(meipass, "models")
        if os.path.isdir(p):
            return p
    return external


def load_font(size):
    for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhl.ttc",
                 "C:/Windows/Fonts/simhei.ttf"):
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_objects(bgr, objects):
    """在 BGR 帧上画检测框 + 中文标签（cv2.putText 无中文字形，故用 PIL）。"""
    img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img)
    font = load_font(max(14, int(img.height * 0.028)))
    for (x0, y0, x1, y1, label, prob) in objects:
        text = "%s %.2f" % (coco_cn.cn(label), prob)
        draw.rectangle([x0, y0, x1, y1], outline=(56, 189, 248), width=3)
        try:
            tw, th = draw.textbbox((0, 0), text, font=font)[2:]
        except Exception:
            tw, th = draw.textsize(text, font=font)
        ty = y0 - th - 6 if y0 - th - 6 > 0 else y0 + 2
        draw.rectangle([x0, ty, x0 + tw + 10, ty + th + 6], fill=(56, 189, 248))
        draw.text((x0 + 5, ty + 2), text, font=font, fill=(17, 24, 39))
    return img


class App(object):
    def __init__(self, root):
        self.root = root
        self.root.title("%s  v%s" % (version.APP_NAME, version.APP_VERSION))
        self.root.configure(bg=BG)
        self.root.geometry("1024x760")

        self.detector = Detector(resource_dir())
        self.log = DetectLog()
        self.log_enabled = True
        self.rows = 0
        self._last_sig = ""
        self._last_log = 0.0

        self.cap = None
        self._stop = threading.Event()
        self._thread = None
        self._q = queue.Queue(maxsize=1)
        self._photo = None
        self.fps = 0.0

        self._build_menu()
        self._build_ui()
        self._load_model_async()

        self.root.after(30, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- 菜单 ----------------
    def _build_menu(self):
        menubar = tk.Menu(self.root, bg=PANEL, fg=FG, tearoff=0)

        rec = tk.Menu(menubar, tearoff=0, bg=PANEL, fg=FG)
        rec.add_command(label="打开记录目录", command=self.open_log_dir)
        rec.add_command(label="清空今日记录", command=self.clear_today)
        rec.add_command(label="删除全部历史", command=self.clear_all)
        menubar.add_cascade(label="记录", menu=rec)

        helpm = tk.Menu(menubar, tearoff=0, bg=PANEL, fg=FG)
        helpm.add_command(label="使用说明", command=self.show_help)
        menubar.add_cascade(label="帮助", menu=helpm)

        menubar.add_command(label="关于", command=self.show_about)
        self.root.config(menu=menubar)

    def show_help(self):
        messagebox.showinfo("帮助", (
            "1. 选择模型与置信度后点「开始检测」，摄像头画面实时显示中文检测框。\n\n"
            "2. 底部状态栏显示当前检测到几个物体、分别是什么，以及帧率。\n\n"
            "3. 检测结果自动存盘：\n    公共「下载」目录 \\ %s \\ detect_日期.csv\n"
            "    字段为 时间、物体、置信度；每天一个文件，历史按天保留。\n\n"
            "4. 菜单「记录」可打开目录、清空今日或删除全部历史。\n\n"
            "5. 检测不到目标时，可把置信度调到 0.35 / 0.25，或换更准的模型（512-lite-c）。"
        ) % DetectLog.SUB_DIR)

    def show_about(self):
        messagebox.showinfo("关于", (
            "%s\n\n版本：%s\n系列：%s（1.x=YOLOv5-Lite；2.x=YOLOv8；3.x=YOLO11；6.x=YOLO26）\n"
            "平台：%s\n引擎：ncnn（CPU）\n\n记录目录：%s"
        ) % (version.APP_NAME, version.APP_VERSION, version.series(), version.PLATFORM, self.log.location))

    def open_log_dir(self):
        try:
            os.startfile(self.log.location)
        except Exception as e:
            messagebox.showwarning("记录目录", "打开失败：%s\n%s" % (self.log.location, e))

    def clear_today(self):
        self.log.clear_today()
        self.rows = 0
        self._update_loginfo()
        messagebox.showinfo("记录", "今日记录已清空（历史按天保留）")

    def clear_all(self):
        if not messagebox.askyesno("记录", "确定删除全部历史记录文件？"):
            return
        n = self.log.clear_all()
        self.rows = 0
        self._update_loginfo()
        messagebox.showinfo("记录", "已删除 %d 个历史文件" % n)

    # ---------------- 界面 ----------------
    def _build_ui(self):
        top = tk.Frame(self.root, bg=PANEL)
        top.pack(fill=tk.X, padx=12, pady=(12, 6))

        tk.Label(top, text="YOLOv5-Lite 实时检测", bg=PANEL, fg=SUB,
                 font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W)
        self.status_var = tk.StringVar(value="正在加载模型…")
        tk.Label(top, textvariable=self.status_var, bg=PANEL, fg=FG,
                 font=("Microsoft YaHei UI", 14, "bold")).pack(anchor=tk.W)

        self.video = tk.Label(self.root, bg="#000000")
        self.video.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        ctrl = tk.Frame(self.root, bg=PANEL)
        ctrl.pack(fill=tk.X, padx=12, pady=(0, 6))

        tk.Label(ctrl, text="模型", bg=PANEL, fg=SUB).pack(side=tk.LEFT, padx=(10, 4))
        self.model_var = tk.StringVar(value=MODELS[DEFAULT_MODEL_INDEX][0])
        cb = ttk.Combobox(ctrl, textvariable=self.model_var, width=20, state="readonly",
                          values=[m[0] for m in MODELS])
        cb.pack(side=tk.LEFT)
        cb.bind("<<ComboboxSelected>>", lambda e: self._load_model_async())

        tk.Label(ctrl, text="置信度", bg=PANEL, fg=SUB).pack(side=tk.LEFT, padx=(14, 4))
        self.th_var = tk.StringVar(value=THRESHOLDS[0][0])
        ttk.Combobox(ctrl, textvariable=self.th_var, width=10, state="readonly",
                     values=[t[0] for t in THRESHOLDS]).pack(side=tk.LEFT)

        tk.Label(ctrl, text="摄像头", bg=PANEL, fg=SUB).pack(side=tk.LEFT, padx=(14, 4))
        self.cam_var = tk.StringVar(value="0")
        ttk.Combobox(ctrl, textvariable=self.cam_var, width=5, state="readonly",
                     values=["0", "1", "2", "3"]).pack(side=tk.LEFT)

        self.btn_start = tk.Button(ctrl, text="开始检测", bg=ACCENT, fg="#0B1220",
                                   relief=tk.FLAT, padx=14, command=self.toggle)
        self.btn_start.pack(side=tk.LEFT, padx=(16, 6))

        self.btn_log = tk.Button(ctrl, text="记录：开", bg="#374151", fg=FG,
                                 relief=tk.FLAT, padx=12, command=self.toggle_log)
        self.btn_log.pack(side=tk.LEFT)

        bottom = tk.Frame(self.root, bg=PANEL)
        bottom.pack(fill=tk.X, padx=12, pady=(0, 12))
        self.loginfo_var = tk.StringVar(value="")
        tk.Label(bottom, textvariable=self.loginfo_var, bg=PANEL, fg=SUB,
                 font=("Microsoft YaHei UI", 9), anchor=tk.W).pack(fill=tk.X, padx=10, pady=6)
        self._update_loginfo()

    def _update_loginfo(self):
        self.loginfo_var.set("记录：%d 条    目录：%s" % (self.rows, self.log.location))

    def _threshold(self):
        for name, v in THRESHOLDS:
            if name == self.th_var.get():
                return v
        return 0.60

    # ---------------- 模型 / 摄像头 ----------------
    def _load_model_async(self):
        idx = DEFAULT_MODEL_INDEX
        for i, m in enumerate(MODELS):
            if m[0] == self.model_var.get():
                idx = i
                break

        def work():
            try:
                name = self.detector.load(idx)
                self.root.after(0, lambda: self.status_var.set("模型已就绪：%s" % name))
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set("模型加载失败：%s" % e))

        threading.Thread(target=work, daemon=True).start()

    def toggle(self):
        if self.cap is None:
            self.start()
        else:
            self.stop()

    def start(self):
        if not self.detector.loaded:
            messagebox.showwarning("模型", "模型尚未加载完成，请稍候")
            return
        idx = int(self.cam_var.get() or 0)
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, 0):
            cap = cv2.VideoCapture(idx, backend) if backend else cv2.VideoCapture(idx)
            if cap.isOpened():
                self.cap = cap
                break
        if self.cap is None or not self.cap.isOpened():
            messagebox.showerror("摄像头", "无法打开摄像头 %d，请检查设备或换一个序号" % idx)
            self.cap = None
            return

        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.btn_start.config(text="停止检测")
        self.status_var.set("检测中…")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        self.cap = None
        self.btn_start.config(text="开始检测")
        self.status_var.set("已停止")
        self.video.config(image="")

    def _loop(self):
        while not self._stop.is_set():
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            t0 = time.time()
            try:
                objects = self.detector.detect(frame, self._threshold())
            except Exception:
                objects = []
            dt = time.time() - t0
            self.fps = (1.0 / dt) if dt > 0 else self.fps

            img = draw_objects(frame, objects)
            self._maybe_log(objects)

            w = max(320, self.video.winfo_width() or 960)
            h = max(240, self.video.winfo_height() or 540)
            img.thumbnail((w, h))
            try:
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(img)
                if not self._q.empty():
                    try:
                        self._q.get_nowait()
                    except Exception:
                        pass
                self._q.put((photo, objects))
            except Exception:
                pass

    def _drain(self):
        try:
            photo, objects = self._q.get_nowait()
        except Exception:
            self.root.after(30, self._drain)
            return
        self._photo = photo          # 防止被 GC
        self.video.config(image=photo)

        if objects:
            counts = {}
            for o in objects:
                counts[coco_cn.cn(o[4])] = counts.get(coco_cn.cn(o[4]), 0) + 1
            desc = "、".join("%s×%d" % (k, v) for k, v in counts.items())
            self.status_var.set("检测到 %d 个：%s    %.0f FPS" % (len(objects), desc, self.fps))
        else:
            self.status_var.set("未检测到物体    %.0f FPS" % self.fps)
        self.root.after(30, self._drain)

    def _maybe_log(self, objects):
        if not self.log_enabled or not objects:
            return
        counts = {}
        for o in objects:
            counts[coco_cn.cn(o[4])] = counts.get(coco_cn.cn(o[4]), 0) + 1
        sig = ";".join("%s:%d" % (k, v) for k, v in sorted(counts.items()))
        now = time.time()
        if sig == self._last_sig or now - self._last_log < 0.7:
            return
        self._last_sig = sig
        self._last_log = now
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for (_, _, _, _, label, prob) in objects:
            if self.log.append(coco_cn.cn(label), prob, ts):
                self.rows += 1
        self.root.after(0, self._update_loginfo)

    def toggle_log(self):
        self.log_enabled = not self.log_enabled
        self.btn_log.config(text="记录：开" if self.log_enabled else "记录：关")

    def on_close(self):
        self.stop()
        self.root.destroy()


# ---------------- 自检（打包后验证用，不需要摄像头） ----------------
def selftest(image_path=None, threshold=0.35):
    """无摄像头自检。windowed 模式看不到控制台，故结果同步写入 _selftest_out.txt。"""
    lines = []

    def say(msg):
        print(msg)
        lines.append(str(msg))

    say("[selftest] 版本 %s (%s / %s)" % (version.APP_VERSION, version.series(), version.PLATFORM))
    d = Detector(resource_dir())
    name = d.load(DEFAULT_MODEL_INDEX)
    say("[selftest] 模型：%s  输入：%d  目录：%s" % (name, d.target_size, resource_dir()))

    img = None
    if image_path and os.path.isfile(image_path):
        img = cv2.imread(image_path)
    if img is None:
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.circle(img, (320, 240), 80, (200, 200, 200), -1)
        say("[selftest] 未指定测试图，使用合成图像")

    t0 = time.time()
    objs = d.detect(img, threshold)
    dt = (time.time() - t0) * 1000
    say("[selftest] 推理 %.1f ms，检出 %d 个目标（阈值 %.2f）" % (dt, len(objs), threshold))
    for (x0, y0, x1, y1, lb, p) in objs[:10]:
        say("   %-6s %.2f  [%.0f,%.0f,%.0f,%.0f]" % (coco_cn.cn(lb), p, x0, y0, x1, y1))

    log = DetectLog()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for (_, _, _, _, lb, p) in objs:
        log.append(coco_cn.cn(lb), p, ts)
    say("[selftest] 记录文件：%s（%d 条）" % (log.path, log.rows_today()))
    say("[selftest] 历史：%s" % (log.history(),))
    say("[selftest] OK" if objs else "[selftest] 无检出（合成图属正常）")

    try:
        out = os.path.join(os.getcwd(), "_selftest_out.txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass
    return 0


def main():
    args = [a for a in sys.argv[1:]]
    if "--selftest" in args:
        img = None
        for a in args:
            if a.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                img = a
        return selftest(img)

    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
