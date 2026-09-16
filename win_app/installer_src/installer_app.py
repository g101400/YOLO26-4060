# -*- coding: utf-8 -*-
"""YOLOv5-Lite检测 —— 自制 Windows 安装 / 卸载引导（零外部工具依赖）

设计（2026-09-16）：
- 不依赖 NSIS / Inno Setup：本机没有这些工具链，用 Python 自身完成全部安装逻辑，
  再用 PyInstaller 打成单文件 exe；快捷方式走系统自带 PowerShell（Windows 组件）。
- 装到 %LOCALAPPDATA%\\Programs\\<应用名>：不需要管理员权限，不弹 UAC。
- 卸载：写 HKCU 卸载注册表项 → 「设置 → 应用」里能看到、能卸载；
  卸载器是同一个 exe 的 --uninstall 模式，删完自身用延迟 cmd 自删。
- 静默模式（--silent --dir=...）供自动化测试与无人值守安装。

用法：
    安装程序.exe                          # 图形向导
    安装程序.exe --silent --dir=D:\\x     # 静默安装到指定目录
    uninstall.exe                         # 卸载（图形确认）
    uninstall.exe --silent                # 静默卸载
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

APP_NAME = "YOLOv5-Lite检测"
APP_EXE = "YOLOv5-Lite检测.exe"
PUBLISHER = "ai-vision"
UNINSTALL_SUBKEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + APP_NAME
CREATE_NO_WINDOW = 0x08000000

try:
    from installer_version import APP_VERSION
except ImportError:                      # 直接以源码跑（开发/自测）
    APP_VERSION = "0.0.0"


def log(msg):
    print(msg, flush=True)


def default_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", APP_NAME)


def self_path():
    return os.path.abspath(sys.executable) if getattr(sys, "frozen", False) \
        else os.path.abspath(__file__)


def find_payload():
    """定位随包资源目录（安装器 exe 旁的 app/，开发态退回 win_app/）。"""
    here = os.path.dirname(self_path())
    cand = os.path.join(here, "app")
    if os.path.isfile(os.path.join(cand, APP_EXE)):
        return cand
    return here                          # 开发态：直接用 win_app 目录


# ---------------- 快捷方式（系统组件 PowerShell，无需管理员） ----------------
def make_shortcut(lnk_path, target, workdir, desc):
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
          "$s.TargetPath='{tgt}';$s.WorkingDirectory='{wd}';"
          "$s.Description='{desc}';$s.Save()").format(
              lnk=lnk_path, tgt=target, wd=workdir, desc=desc)
    rc = subprocess.call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-Command", ps], creationflags=CREATE_NO_WINDOW)
    return rc == 0 and os.path.isfile(lnk_path)


def desktop_dir():
    # 真实桌面（OneDrive 重定向也兼容）
    ps = "[Environment]::GetFolderPath('Desktop')"
    try:
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps],
                                      creationflags=CREATE_NO_WINDOW).decode("gbk", "replace").strip()
        if out and os.path.isdir(out):
            return out
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


# ---------------- 安装 ----------------
def install(payload, target, desktop=True, startmenu=True, launch=False):
    if not os.path.isfile(os.path.join(payload, APP_EXE)):
        raise SystemExit("安装包不完整：缺少 %s（在 %s 下）" % (APP_EXE, payload))
    os.makedirs(target, exist_ok=True)
    log("① 复制程序与模型 → %s" % target)
    for name in sorted(os.listdir(payload)):
        src = os.path.join(payload, name)
        dst = os.path.join(target, name)
        if os.path.isdir(src):
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        elif name != os.path.basename(self_path()):
            shutil.copy2(src, dst)

    log("② 写入卸载器与注册表")
    uninst = os.path.join(target, "uninstall.exe")
    try:
        shutil.copyfile(self_path(), uninst)      # frozen 下即自身 exe
    except Exception as e:
        log("   卸载器复制失败（不影响使用，可手动删目录）：%s" % e)

    try:
        import winreg
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_SUBKEY)
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, target)
        winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, os.path.join(target, APP_EXE))
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, '"%s" --uninstall' % uninst)
        winreg.SetValueEx(k, "QuietUninstallString", 0, winreg.REG_SZ, '"%s" --uninstall --silent' % uninst)
        size_kb = 0
        for root, _, files in os.walk(target):
            for f in files:
                try:
                    size_kb += os.path.getsize(os.path.join(root, f)) // 1024
                except OSError:
                    pass
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(k)
    except Exception as e:
        log("   注册表写入失败（不影响安装）：%s" % e)

    shortcuts = []
    if desktop:
        lnk = os.path.join(desktop_dir(), APP_NAME + ".lnk")
        if make_shortcut(lnk, os.path.join(target, APP_EXE), target, APP_NAME):
            shortcuts.append(lnk)
    if startmenu:
        sm = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                          "Start Menu", "Programs")
        lnk = os.path.join(sm, APP_NAME + ".lnk")
        if make_shortcut(lnk, os.path.join(target, APP_EXE), target, APP_NAME):
            shortcuts.append(lnk)
    log("③ 快捷方式：%s" % ("、".join(shortcuts) if shortcuts else "未创建"))

    if launch:
        subprocess.Popen([os.path.join(target, APP_EXE)], cwd=target)
    log("✔ 安装完成（%s）" % target)
    return True


# ---------------- 卸载 ----------------
def uninstall(target):
    if not os.path.isdir(target):
        log("目录不存在，无需卸载：%s" % target)
    else:
        log("① 结束正在运行的 %s" % APP_EXE)
        subprocess.call(["taskkill", "/F", "/IM", APP_EXE],
                        creationflags=CREATE_NO_WINDOW,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("② 删除快捷方式")
        for lnk in (os.path.join(desktop_dir(), APP_NAME + ".lnk"),
                    os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                                 "Start Menu", "Programs", APP_NAME + ".lnk")):
            if os.path.isfile(lnk):
                try:
                    os.remove(lnk)
                except OSError as e:
                    log("   跳过 %s：%s" % (lnk, e))
        log("③ 删除注册表卸载项")
        try:
            import winreg
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_SUBKEY)
        except Exception as e:
            log("   %s" % e)
        log("④ 删除程序目录（卸载器自身延迟自删）")
        me = os.path.abspath(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.abspath(__file__)
        tmp_copy = os.path.join(tempfile.gettempdir(), "_uninst_cleanup_%d.exe" % os.getpid())
        try:
            shutil.copyfile(me, tmp_copy)
        except Exception:
            tmp_copy = None
        rmdir = 'rmdir /s /q "%s"' % target
        extra = ('& del /q "%s"' % tmp_copy) if tmp_copy else ""
        subprocess.Popen('ping -n 3 127.0.0.1 >nul & ' + rmdir + extra,
                         shell=True, creationflags=0x00000008)   # DETACHED_PROCESS
    log("✔ 卸载完成")
    return True


# ---------------- 图形向导 ----------------
def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    payload = find_payload()
    root = tk.Tk()
    root.title("%s 安装向导" % APP_NAME)
    root.resizable(False, False)
    tk.Label(root, text="%s  v%s" % (APP_NAME, APP_VERSION),
             font=("Microsoft YaHei", 14, "bold")).pack(pady=(14, 2))
    tk.Label(root, text="将安装到本机用户目录，无需管理员权限",
             fg="#666").pack()

    frm = tk.Frame(root)
    frm.pack(padx=16, pady=10, fill="x")
    var_dir = tk.StringVar(value=default_dir())
    tk.Label(frm, text="安装位置：").grid(row=0, column=0, sticky="e")
    tk.Entry(frm, textvariable=var_dir, width=46).grid(row=0, column=1, padx=4)
    frm.columnconfigure(1, weight=1)

    def browse():
        var_dir.set(filedialog.askdirectory(initialdir=var_dir.get()) or var_dir.get())
    tk.Button(frm, text="浏览…", command=browse).grid(row=0, column=2)

    var_desktop = tk.BooleanVar(value=True)
    var_menu = tk.BooleanVar(value=True)
    var_run = tk.BooleanVar(value=False)
    opts = tk.Frame(root)
    opts.pack(padx=16, pady=2, fill="x")
    tk.Checkbutton(opts, text="创建桌面快捷方式", variable=var_desktop).pack(anchor="w")
    tk.Checkbutton(opts, text="创建开始菜单快捷方式", variable=var_menu).pack(anchor="w")
    tk.Checkbutton(opts, text="安装完成后立即运行", variable=var_run).pack(anchor="w")

    def do_install():
        try:
            install(payload, var_dir.get().strip(),
                    desktop=var_desktop.get(), startmenu=var_menu.get(),
                    launch=var_run.get())
            messagebox.showinfo("完成", "%s 安装完成！\n\n卸载：Windows「设置 → 应用」或安装目录内 uninstall.exe" % APP_NAME)
            root.destroy()
        except Exception as e:
            messagebox.showerror("安装失败", str(e))
    tk.Button(root, text="立即安装", width=18, bg="#2f7ae0", fg="white",
              command=do_install).pack(pady=14)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uninstall", action="store_true", help="卸载模式")
    ap.add_argument("--silent", action="store_true", help="静默（无界面）")
    ap.add_argument("--dir", dest="dir_", default=None, help="安装目录")
    ap.add_argument("--no-shortcuts", action="store_true", help="不建快捷方式（测试用）")
    args = ap.parse_args()

    target = args.dir_ or default_dir()
    if args.uninstall:
        target = args.dir_ or read_install_location() or default_dir()
        if not args.silent:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk(); r.withdraw()
            if not messagebox.askyesno("卸载确认", "确定要卸载 %s 吗？\n\n（个人数据与导出文件不在安装目录内，将被保留）" % APP_NAME):
                return
        uninstall(target)
    else:
        if args.silent:
            install(find_payload(), target,
                    desktop=not args.no_shortcuts, startmenu=not args.no_shortcuts)
        else:
            gui()


if __name__ == "__main__":
    main()
