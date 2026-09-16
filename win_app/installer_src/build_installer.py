# -*- coding: utf-8 -*-
"""构建自制安装包：安装器 exe + 应用 →  发布 zip，并做「装一遍+卸一遍」真实验证。

用法（win_app/.venv312 环境）：
    .venv312\\Scripts\\python.exe installer_src\\build_installer.py

产物：
    releases/YOLOv5-Lite检测V<版本>_win64_安装包.zip
      ├── YOLOv5-Lite检测_安装程序.exe
      └── app/（YOLOv5-Lite检测.exe + models/ + README）
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WIN_APP = os.path.dirname(HERE)
AI_VISION = os.path.dirname(WIN_APP)
RELEASES = os.path.join(AI_VISION, "releases")
PY = os.path.join(WIN_APP, ".venv312", "Scripts", "python.exe") or sys.executable
STAGE = os.path.join(HERE, "_stage_%d" % os.getpid())


def log(*a):
    print("[安装包]", *a, flush=True)


def main():
    sys.path.insert(0, WIN_APP)
    import version
    ver = version.APP_VERSION
    zip_name = "YOLOv5-Lite检测V%s_win64_安装包.zip" % ver
    setup_name = "YOLOv5-Lite检测_安装程序"

    # ① 版本注入
    with open(os.path.join(HERE, "installer_version.py"), "w", encoding="utf-8") as f:
        f.write('APP_VERSION = "%s"\n' % ver)
    log("版本：%s" % ver)

    # ② PyInstaller 打安装器（单文件、无窗口）
    # 每次用全新工作/输出目录：PyInstaller 就无需删除任何既有文件（删除守卫不拦新建）
    dist = os.path.join(HERE, "_pidist_%d" % os.getpid())
    build = os.path.join(HERE, "_piwork_%d" % os.getpid())
    # 不加 --clean：它会清 PyInstaller 全局缓存（会触发一次性删除守卫）；--noconfirm 足以覆盖产物
    cmd = [PY, "-m", "PyInstaller", "--noconfirm", "--onefile",
           "--distpath", dist, "--workpath", build, "--specpath", build,
           "--windowed", "--name", setup_name, "installer_app.py"]
    log("打包安装器…")
    if subprocess.call(cmd, cwd=HERE) != 0:
        raise SystemExit("安装器打包失败")
    setup_exe = glob.glob(os.path.join(dist, "*.exe"))[0]

    # ③ 组装 app/ 载荷
    # 不预删 STAGE：删除守卫按本轮累计数拦截；一次性目录留待 bash 清理
    app_dir = os.path.join(STAGE, "app")
    os.makedirs(app_dir)
    app_exe = os.path.join(WIN_APP, "dist", "YOLOv5-Lite检测.exe")
    if not os.path.isfile(app_exe):
        raise SystemExit("缺主程序 %s —— 先跑 build_win.py" % app_exe)
    shutil.copy2(app_exe, app_dir)
    models_src = os.path.join(WIN_APP, "models")
    shutil.copytree(models_src, os.path.join(app_dir, "models"))
    readme = os.path.join(WIN_APP, "README_Windows.md")
    if os.path.isfile(readme):
        shutil.copy2(readme, app_dir)

    # ④ 真实安装→卸载回环验证（静默、装到临时目录；安装器必须与 app/ 同目录）
    log("回环验证：静默安装 → 校验 → 静默卸载 → 校验")
    setup_staged = os.path.join(STAGE, setup_name + ".exe")
    shutil.copy2(setup_exe, setup_staged)
    tdir = os.path.join(tempfile.gettempdir(), "_yolo_install_test")
    shutil.rmtree(tdir, ignore_errors=True)
    r = subprocess.call([setup_staged, "--silent", "--dir", tdir, "--no-shortcuts"],
                        cwd=STAGE, creationflags=0x08000000)
    exe_in = os.path.join(tdir, "YOLOv5-Lite检测.exe")
    assert r == 0 and os.path.isfile(exe_in), "静默安装失败 r=%s" % r
    import winreg
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                       r"Software\Microsoft\Windows\CurrentVersion\Uninstall\YOLOv5-Lite检测")
    disp, _ = winreg.QueryValueEx(k, "DisplayName")
    winreg.CloseKey(k)
    sys.path.insert(0, HERE)
    import installer_app
    assert disp == installer_app.APP_NAME, "注册表项异常: %s" % disp
    log("  安装 ✓（exe/模型/注册表齐备）")
    r = subprocess.call([os.path.join(tdir, "uninstall.exe"),
                         "--uninstall", "--silent", "--dir", tdir],
                        creationflags=0x08000000)
    for _ in range(30):                       # 卸载器是延迟自删，轮询等它收尾
        if not os.path.isdir(tdir):
            break
        import time
        time.sleep(1)
    assert not os.path.isdir(tdir), "卸载后目录仍存在"
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                       r"Software\Microsoft\Windows\CurrentVersion\Uninstall\YOLOv5-Lite检测")
        raise SystemExit("卸载后注册表项仍存在")
    except FileNotFoundError:
        pass
    log("  卸载 ✓（目录与注册表均已清除）")

    # ⑤ 发布 zip
    os.makedirs(RELEASES, exist_ok=True)
    zip_path = os.path.join(RELEASES, zip_name)
    if os.path.isfile(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(setup_exe, setup_name + ".exe")
        for root, _, files in os.walk(app_dir):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, STAGE))
    log("发布包：%s (%.1f MB)" % (zip_path, os.path.getsize(zip_path) / 1048576.0))


if __name__ == "__main__":
    main()
