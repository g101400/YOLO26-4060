# -*- coding: utf-8 -*-
"""Windows 版打包脚本：PyInstaller → exe → 发布 zip。

用法（在 Python 3.12 虚拟环境里执行，需 tkinter）：
    .venv312\\Scripts\\python.exe build_win.py

产物：
    dist/YOLOv5-Lite检测.exe            （单文件，已内置模型）
    releases/YOLOv5-Lite检测V<版本>_win64.zip（exe + 可替换的 models/ + 说明）
"""
import glob
import os
import shutil
import subprocess
import sys
import zipfile

import version

HERE = os.path.dirname(os.path.abspath(__file__))
AI_VISION = os.path.dirname(HERE)
ASSETS = os.path.join(AI_VISION, "YOLOv5-Lite-v1.5", "android_demo",
                      "ncnn-android-v5lite", "app", "src", "main", "assets")
MODELS = os.path.join(HERE, "models")
DIST = os.path.join(HERE, "dist")
BUILD = os.path.join(HERE, "build")
RELEASES = os.path.join(AI_VISION, "releases")
EXE_NAME = "YOLOv5-Lite检测"
ZIP_NAME = "YOLOv5-Lite检测V%s_win64.zip" % version.APP_VERSION


def log(*a):
    print("[win]", *a, flush=True)


def pick_python():
    """优先用带 tkinter 的 .venv312；否则用当前解释器。"""
    cand = os.path.join(HERE, ".venv312", "Scripts", "python.exe")
    if os.path.isfile(cand):
        return cand
    return sys.executable


def sync_models():
    """模型与安卓端同源（直接取安卓 assets 的 .param/.bin）。"""
    os.makedirs(MODELS, exist_ok=True)
    n = 0
    for ext in ("*.param", "*.bin"):
        for f in glob.glob(os.path.join(ASSETS, ext)):
            dst = os.path.join(MODELS, os.path.basename(f))
            if not os.path.isfile(dst) or os.path.getmtime(f) > os.path.getmtime(dst):
                shutil.copy2(f, dst)
                n += 1
    log("模型同步：新增/更新 %d 个 → %s" % (n, MODELS))
    if not glob.glob(os.path.join(MODELS, "*.param")):
        raise SystemExit("未找到任何 .param 模型，检查路径：%s" % ASSETS)


def build_exe(py):
    for stale in (DIST, BUILD):
        if os.path.isdir(stale):
            shutil.rmtree(stale, ignore_errors=True)

    cmd = [py, "-m", "PyInstaller",
           "--noconfirm", "--clean", "--onefile", "--windowed",
           "--name", EXE_NAME,
           # Windows 下 --add-data 的分隔符是 ;（os.pathsep）
           "--add-data", "models" + os.pathsep + "models",
           "--collect-all", "ncnn",
           "--hidden-import", "ncnn",
           "app.py"]
    log("打包命令：%s" % " ".join(cmd))
    rc = subprocess.call(cmd, cwd=HERE)
    if rc != 0:
        log("中文名打包失败(rc=%s)，改用 ASCII 名重试" % rc)
        cmd[cmd.index("--name") + 1] = "YOLOv5LiteDetect"
        rc = subprocess.call(cmd, cwd=HERE)
    if rc != 0:
        raise SystemExit("PyInstaller 失败 rc=%s" % rc)

    exes = glob.glob(os.path.join(DIST, "*.exe"))
    if not exes:
        raise SystemExit("未产出 exe")
    return exes[0]


def make_zip(exe):
    os.makedirs(RELEASES, exist_ok=True)
    zip_path = os.path.join(RELEASES, ZIP_NAME)
    if os.path.isfile(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, os.path.basename(exe))
        for f in sorted(glob.glob(os.path.join(MODELS, "*"))):
            z.write(f, "models/" + os.path.basename(f))
        readme = os.path.join(HERE, "README_Windows.md")
        if os.path.isfile(readme):
            z.write(readme, "README_Windows.md")
    log("发布包：%s (%.1f MB)" % (zip_path, os.path.getsize(zip_path) / 1048576.0))
    return zip_path


def main():
    py = pick_python()
    log("解释器：%s" % py)
    sync_models()
    exe = build_exe(py)
    log("exe：%s (%.1f MB)" % (exe, os.path.getsize(exe) / 1048576.0))

    # 自检：用打包后的 exe 跑一遍真实图片（--selftest 无需摄像头）
    test_img = os.path.join(AI_VISION, "YOLOv5-Lite-v1.5", "python_demo", "openvino", "bike.jpg")
    cmd = [exe, "--selftest"]
    if os.path.isfile(test_img):
        cmd.append(test_img)
    out = os.path.join(HERE, "_selftest_out.txt")
    if os.path.isfile(out):
        os.remove(out)
    rc = subprocess.call(cmd, cwd=HERE)
    log("exe 自检 rc=%s" % rc)
    if os.path.isfile(out):
        with open(out, encoding="utf-8") as f:
            log("exe 自检输出：\n" + f.read().rstrip())

    zip_path = make_zip(exe)
    log("DONE -> %s" % zip_path)


if __name__ == "__main__":
    main()
