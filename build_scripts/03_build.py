# Phase 3: 仅修正 local.properties（正斜杠，避免 Java Properties 把 \n 当换行转义）
# 并重跑 gradlew assembleDebug。SDK 组件已在 Phase 2 安装完毕，无需再装。
import os, sys, subprocess

JDK     = r'E:\jdk11'
SDK     = r'E:\AndroidSDK'
PROJECT = r'D:\Users\WorkBuddy\ai-vision\YOLOv5-Lite-v1.5\android_demo\ncnn-android-v5lite'
GRADLEW = os.path.join(PROJECT, 'gradlew.bat')

def log(*a): print('[p3]', *a, flush=True)

# --- 修正 local.properties（全部正斜杠）---
lp = os.path.join(PROJECT, 'local.properties')
out = [
    '## 本机 E 盘 Android 构建链（2026-09-15 自动生成，正斜杠避免 \\n 转义）',
    'sdk.dir=E:/AndroidSDK',
    'ndk.dir=E:/AndroidSDK/ndk/21.3.6528147',
    'cmake.dir=E:/AndroidSDK/cmake/3.10.2.4988404',
]
with open(lp, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out) + '\n')
log('local.properties rewritten:\n' + '\n'.join(out))

# --- 设置环境（JDK 11 给 Gradle 5.4.1）---
e = os.environ.copy()
e['JAVA_HOME'] = JDK
e['PATH'] = os.path.join(JDK, 'bin') + ';' + e.get('PATH', '')

# --- 重跑 assembleDebug ---
log('building app-debug.apk ...')
p = subprocess.run('cmd.exe /c "%s" assembleDebug --no-daemon --stacktrace' % GRADLEW,
                   cwd=PROJECT, env=e, capture_output=False, text=True,
                   shell=True, timeout=5400)
log('gradle assembleDebug rc=%s' % p.returncode)

import glob as _glob
_apk_candidates = _glob.glob(os.path.join(PROJECT, 'app', 'build', 'outputs', 'apk', 'debug', '*.apk'))
apk = _apk_candidates[0] if _apk_candidates else None
if p.returncode == 0 and apk and os.path.exists(apk):
    log('BUILD SUCCESS -> %s (%d bytes)' % (apk, os.path.getsize(apk)))
else:
    log('BUILD FAILED rc=%s apk=%s' % (p.returncode, apk))
    sys.exit(2)
