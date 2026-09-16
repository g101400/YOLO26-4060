# Phase 2: 安装 SDK 组件并编译 APK
# 通过 python subprocess 直接调用 cmd.exe /c *.bat，绕开本机坏 bash wrapper。
# 前置: 01_download.py 已完成 (E:\jdk11, E:\AndroidSDK\cmdline-tools\latest, ncnn, opencv-mobile, models)
import os, sys, subprocess, time

JDK     = r'E:\jdk11'
SDK     = r'E:\AndroidSDK'
PROJECT = r'D:\Users\WorkBuddy\ai-vision\YOLOv5-Lite-v1.5\android_demo\ncnn-android-v5lite'
SDK_MGR = os.path.join(SDK, 'cmdline-tools', 'latest', 'bin', 'sdkmanager.bat')
GRADLEW = os.path.join(PROJECT, 'gradlew.bat')
LOGDIR  = r'E:\tmp_android_dl'
os.makedirs(LOGDIR, exist_ok=True)

def env():
    e = os.environ.copy()
    e['JAVA_HOME'] = JDK
    e['PATH'] = os.path.join(JDK, 'bin') + ';' + os.path.join(SDK, 'cmdline-tools', 'latest', 'bin') + ';' + e.get('PATH', '')
    return e

def log(*a):
    print('[p2]', *a, flush=True)

def run_cmd(args_str, cwd=None, input_text=None, timeout=3600):
    """用 cmd.exe /c 执行整条命令字符串，输出来自 bat 自身。"""
    full = 'cmd.exe /c ' + args_str
    log('RUN:', full)
    p = subprocess.run(full, cwd=cwd, env=env(), input=input_text,
                       capture_output=False, text=True, timeout=timeout, shell=True)
    return p.returncode

def fail(msg):
    log('FATAL:', msg)
    sys.exit(1)

# --- 前置校验 ---
if not os.path.exists(os.path.join(JDK, 'bin', 'java.exe')):
    fail('JDK 缺失: %s (phase1 未成功下载 JDK)' % JDK)
if not os.path.exists(SDK_MGR):
    fail('sdkmanager 缺失: %s (phase1 未成功下载 cmdline-tools)' % SDK_MGR)

# --- 0) sdkmanager 版本自检 ---
rc = run_cmd('"%s" --version' % SDK_MGR)
log('sdkmanager --version rc=%s' % rc)

# --- 1) 接受 license (喂入若干 y) ---
log('accept licenses ...')
run_cmd('"%s" --licenses' % SDK_MGR, input_text='y\n' * 40)
log('licenses done')

# --- 2) 安装组件 ---
pkgs = 'platforms;android-24 build-tools;29.0.2 ndk;21.3.6528147 cmake;3.10.2.4988404'
log('installing: %s' % pkgs)
rc = run_cmd('"%s" %s' % (SDK_MGR, pkgs), timeout=5400, input_text='y\n' * 60)
log('sdk install rc=%s' % rc)

# 校验关键目录
need = [
    os.path.join(SDK, 'platforms', 'android-24'),
    os.path.join(SDK, 'build-tools', '29.0.2'),
    os.path.join(SDK, 'ndk', '21.3.6528147'),
    os.path.join(SDK, 'cmake', '3.10.2.4988404'),
]
for d in need:
    log(('OK   ' if os.path.isdir(d) else 'MISS ') + d)
missing = [d for d in need if not os.path.isdir(d)]
if missing:
    fail('SDK 组件缺失: %s' % missing)

# --- 3) local.properties 路径核对 (防止实际解压路径与预期不符) ---
lp = os.path.join(PROJECT, 'local.properties')
lines = []
if os.path.exists(lp):
    with open(lp, encoding='utf-8') as f:
        lines = f.read().splitlines()
cmake_dir = os.path.join(SDK, 'cmake', '3.10.2.4988404')
ndk_dir   = os.path.join(SDK, 'ndk', '21.3.6528147')
out = []
for ln in lines:
    if ln.startswith('sdk.dir='):   out.append('sdk.dir=' + SDK.replace('\\', '/'))
    elif ln.startswith('ndk.dir='): out.append('ndk.dir=' + ndk_dir.replace('\\', '/'))
    elif ln.startswith('cmake.dir='): out.append('cmake.dir=' + cmake_dir.replace('\\', '/'))
    else: out.append(ln)
# 补齐缺失键
have = {l.split('=')[0] for l in out if '=' in l}
if 'sdk.dir' not in have:   out.append('sdk.dir=' + SDK.replace('\\', '/'))
if 'ndk.dir' not in have:   out.append('ndk.dir=' + ndk_dir.replace('\\', '/'))
if 'cmake.dir' not in have: out.append('cmake.dir=' + cmake_dir.replace('\\', '/'))
with open(lp, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out) + '\n')
log('local.properties synced:\n' + '\n'.join(out))

# --- 4) 编译 assembleDebug ---
log('building app-debug.apk ...')
rc = run_cmd('"%s" assembleDebug --no-daemon --stacktrace' % GRADLEW, cwd=PROJECT, timeout=5400)
log('gradle assembleDebug rc=%s' % rc)

apk = os.path.join(PROJECT, 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk')
if rc == 0 and os.path.exists(apk):
    log('BUILD SUCCESS -> %s (%d bytes)' % (apk, os.path.getsize(apk)))
else:
    log('BUILD FAILED rc=%s apk_exists=%s' % (rc, os.path.exists(apk)))
    sys.exit(2)
