# Phase 1: 下载并解压 Android 构建链（不含 SDK 组件，组件由 02 用 sdkmanager 安装）
# 环境约束（实测 2026-09-15）：
#   - 本机 bash wrapper 损坏：dir/head/tail/mkdir/sleep 均不可用 -> 文件操作用 python 标准库
#   - 代理：github release CDN 偶发 502；raw.githubusercontent 直连 SSL EOF -> 模型走 ghproxy.net
#   - maven.google.com 被代理 502 -> 构建依赖改用阿里云镜像（见 build.gradle）
#   - 沙箱 safe-delete：删除 >50 文件需确认（非交互会卡死）-> 全程不调用 shutil.move/rmtree，
#     改为「解压直接落最终目录（剥离顶层目录）」，只写不删。
# 关键修正：每个组件起步先删本组件残留 .part（避免跨轮续传把上一轮损坏的 24MB 续成坏压缩包）。
import os, sys, time, json, glob, shutil, urllib.request, urllib.error, zipfile

SDK    = r'E:\AndroidSDK'
TMP    = r'E:\tmp_android_dl'
JDK    = r'E:\jdk11'
ASSETS = r'D:\Users\WorkBuddy\ai-vision\YOLOv5-Lite-v1.5\android_demo\ncnn-android-v5lite\app\src\main\assets'
PROXY  = 'https://ghproxy.net/'
os.makedirs(SDK, exist_ok=True)
os.makedirs(TMP, exist_ok=True)

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def log(*a):
    print('[dl]', *a, flush=True)

def is_zip(path):
    try:
        with open(path, 'rb') as f:
            return f.read(4) == b'PK\x03\x04'
    except Exception:
        return False

def download(url, dest, tries=12, timeout=600):
    """干净起步 + 断点续传(仅本轮内) + 退避重试。成功返回 True。"""
    part = dest + '.part'
    if os.path.exists(part):
        try: os.remove(part)
        except Exception: pass
    last_err = ''
    for attempt in range(1, tries + 1):
        try:
            headers = dict(UA)
            start = os.path.getsize(part) if os.path.exists(part) else 0
            if start:
                headers['Range'] = 'bytes=%d-' % start
            log('GET [%d/%d] %s%s' % (attempt, tries, url, (' (resume %d)' % start) if start else ''))
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                mode = 'ab' if (start and r.status == 206) else 'wb'
                with open(part, mode) as f:
                    while True:
                        buf = r.read(1 << 20)
                        if not buf:
                            break
                        f.write(buf)
            # 下载后校验（JDK 等二进制必须为真 zip）
            if dest.endswith('.zip') and not is_zip(part):
                raise IOError('downloaded file is not a valid zip')
            sz = os.path.getsize(part)
            os.replace(part, dest)
            log('  ->', dest, sz, 'bytes')
            return True
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionError, EOFError, IOError) as e:
            last_err = repr(e)
            log('  !! attempt %d failed: %s' % (attempt, last_err[:140]))
            if os.path.exists(part):
                try: os.remove(part)   # 损坏的部分作废，下轮干净重下
                except Exception: pass
            if attempt < tries:
                time.sleep(min(3 * attempt, 25))
    log('  XX give up: %s  (last: %s)' % (url, last_err[:140]))
    return False

def extract_strip(zippath, destroot):
    """解压并剥离顶层目录，直接落到 destroot（只写不删，规避 safe-delete）。"""
    os.makedirs(destroot, exist_ok=True)
    n = 0
    with zipfile.ZipFile(zippath) as z:
        for info in z.infolist():
            parts = info.filename.split('/')
            if len(parts) <= 1:
                continue
            rel = '/'.join(parts[1:])
            if not rel:
                continue
            target = os.path.join(destroot, rel)
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(info) as src, open(target, 'wb') as f:
                    shutil.copyfileobj(src, f)
                n += 1
    log('extracted(strip) %s -> %s  (%d files)' % (os.path.basename(zippath), destroot, n))

def extract_all(zippath, destroot):
    with zipfile.ZipFile(zippath) as z:
        z.extractall(destroot)
    log('extracted %s -> %s' % (os.path.basename(zippath), destroot))

status = {}

# 0) JDK 11 -> E:\jdk11  (adoptium API 直连最稳；不走 adoptium github release(502)/ghproxy(大文件截断))
jdk_candidates = [
    'https://api.adoptium.net/v3/binary/latest/11/ga/windows/x64/jdk/hotspot/normal/eclipse',
    'https://api.adoptium.net/v3/binary/version/jdk-11.0.24+8/11/ga/windows/x64/jdk/hotspot/normal/eclipse',
]
jdk_zip = os.path.join(TMP, 'jdk11.zip')
jdk_ok = False
if os.path.exists(os.path.join(JDK, 'bin', 'java.exe')):
    log('JDK already present:', JDK); jdk_ok = True
else:
    for u in jdk_candidates:
        if download(u, jdk_zip):
            try:
                extract_strip(jdk_zip, JDK)
                assert os.path.exists(os.path.join(JDK, 'bin', 'java.exe')), 'java.exe 缺失'
                jdk_ok = True
                log('JDK ready:', JDK)
                break
            except Exception as e:
                log('  !! JDK 解压失败:', repr(e)[:160])
    if not jdk_ok:
        log('WARN: JDK 下载失败(稍后单独重试)')
status['jdk'] = jdk_ok

# 1) cmdline-tools -> E:\AndroidSDK\cmdline-tools\latest  (剥离顶层 cmdline-tools/)
try:
    zt = os.path.join(TMP, 'cmdtools.zip')
    if download('https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip', zt):
        extract_strip(zt, os.path.join(SDK, 'cmdline-tools', 'latest'))
        assert os.path.exists(os.path.join(SDK, 'cmdline-tools', 'latest', 'bin', 'sdkmanager.bat')), 'sdkmanager.bat 缺失!'
        log('cmdline-tools ready')
        status['cmdline-tools'] = True
    else:
        status['cmdline-tools'] = False
except Exception as e:
    log('WARN: cmdline-tools 失败:', repr(e)[:160])
    status['cmdline-tools'] = False

# 2) ncnn -> E:\AndroidSDK\ncnn-20210525-android-vulkan  (github 直连可用，ghproxy 兜底)
try:
    zn = os.path.join(TMP, 'ncnn.zip')
    u1 = 'https://github.com/Tencent/ncnn/releases/download/20210525/ncnn-20210525-android-vulkan.zip'
    if download(u1, zn) or download(PROXY + u1, zn):
        extract_all(zn, SDK)
        assert os.path.isdir(os.path.join(SDK, 'ncnn-20210525-android-vulkan')), 'ncnn 解压失败'
        log('ncnn ready'); status['ncnn'] = True
    else:
        status['ncnn'] = False
except Exception as e:
    log('WARN: ncnn 失败:', repr(e)[:160]); status['ncnn'] = False

# 3) opencv-mobile -> E:\AndroidSDK\opencv-mobile-2.4.13.7-android
try:
    zo = os.path.join(TMP, 'ocv.zip')
    u2 = 'https://github.com/nihui/opencv-mobile/releases/download/v36/opencv-mobile-2.4.13.7-android.zip'
    if download(u2, zo) or download(PROXY + u2, zo):
        extract_all(zo, SDK)
        assert os.path.isdir(os.path.join(SDK, 'opencv-mobile-2.4.13.7-android')), 'opencv-mobile 解压失败'
        log('opencv-mobile ready'); status['opencv-mobile'] = True
    else:
        status['opencv-mobile'] = False
except Exception as e:
    log('WARN: opencv-mobile 失败:', repr(e)[:160]); status['opencv-mobile'] = False

# 4) 模型 v5lite 各变体 -> assets  (raw 直连 SSL EOF -> ghproxy；best-effort)
try:
    api = 'https://api.github.com/repos/ppogg/ncnn-android-v5lite/contents/app/src/main/assets'
    req = urllib.request.Request(api, headers=UA)
    data = json.load(urllib.request.urlopen(req, timeout=60))
    names = [f['name'] for f in data if f['name'].endswith(('.param', '.bin'))]
    log('model files in repo:', names)
    ok_models = 0
    for n in names:
        raw = 'https://raw.githubusercontent.com/ppogg/ncnn-android-v5lite/master/app/src/main/assets/' + n
        if download(PROXY + raw, os.path.join(ASSETS, n)) or download(raw, os.path.join(ASSETS, n)):
            ok_models += 1
        else:
            log('  !! model 失败:', n)
    log('models ready:', ok_models, '/', len(names), 'in', ASSETS)
    status['models'] = (ok_models, len(names))
except Exception as e:
    log('WARN: 模型清单/下载失败:', repr(e)[:160]); status['models'] = (0, 0)

log('==== SUMMARY ====')
for k, v in status.items():
    log('  %-15s %s' % (k, v))
log('PHASE1 DONE')
with open(os.path.join(SDK, '_phase1_done.txt'), 'w') as f:
    f.write('PHASE1 DONE\n')
    for k, v in status.items():
        f.write('%s=%s\n' % (k, v))
    f.write('ncnn=%s\n' % os.path.join(SDK, 'ncnn-20210525-android-vulkan'))
    f.write('ocv=%s\n' % os.path.join(SDK, 'opencv-mobile-2.4.13.7-android'))
    f.write('models_in=%s\n' % ASSETS)
