# 下载 Java-11 兼容的旧版 cmdline-tools (7.0 / 8512546) 并覆盖到 latest。
# 关键点：绝不调用 rmtree（>50 文件会触发沙箱 safe-delete 卡死）。直接覆盖写入即可。
import os, sys, zipfile, urllib.request, time

TMP = r'E:\tmp_android_dl'
SDK = r'E:\AndroidSDK'
LATEST = os.path.join(SDK, 'cmdline-tools', 'latest')
URL = 'https://dl.google.com/android/repository/commandlinetools-win-8512546_latest.zip'
UA = {'User-Agent': 'Mozilla/5.0'}
os.makedirs(TMP, exist_ok=True)
ZIP = os.path.join(TMP, 'cmdtools_j11.zip')

def log(*a): print('[ct]', *a, flush=True)

def is_valid_zip(p):
    if not os.path.exists(p) or os.path.getsize(p) < 5_000_000:
        return False
    with open(p, 'rb') as f:
        return f.read(4) == b'PK\x03\x04'

def download(url, dst, retries=12):
    if is_valid_zip(dst):
        log('zip 已存在且有效，跳过下载: %s' % dst)
        return True
    for i in range(1, retries + 1):
        try:
            if os.path.exists(dst):
                os.remove(dst)
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r, open(dst, 'wb') as f:
                while True:
                    buf = r.read(1 << 20)
                    if not buf:
                        break
                    f.write(buf)
            if not is_valid_zip(dst):
                raise IOError('not a valid zip')
            log('downloaded %s (%d bytes)' % (dst, os.path.getsize(dst)))
            return True
        except Exception as e:
            log('attempt %d failed: %r' % (i, e))
            time.sleep(min(8 * i, 40))
    return False

def extract_overwrite(zip_path, out_dir):
    # 直接覆盖写入，不删除 out_dir（避免 safe-delete 卡死）
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename
            if name.endswith('/'):
                continue
            parts = name.split('/')
            rel = '/'.join(parts[1:]) if len(parts) > 1 else name
            if not rel:
                continue
            target = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, 'wb') as dst:
                dst.write(src.read())
    log('extracted(overwrite) %s -> %s' % (zip_path, out_dir))

if not download(URL, ZIP):
    log('FATAL: 下载旧版 cmdline-tools 失败')
    sys.exit(1)
extract_overwrite(ZIP, LATEST)
sm = os.path.join(LATEST, 'bin', 'sdkmanager.bat')
log('sdkmanager exists: %s -> %s' % (os.path.exists(sm), sm))
log('CMDTOOLS J11 DONE')
