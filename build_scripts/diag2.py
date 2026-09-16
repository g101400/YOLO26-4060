# 诊断2：实测各 GitHub 代理能否真正下发二进制（Range 取前 2KB）
import urllib.request, time

UA = {'User-Agent': 'Mozilla/5.0'}

# 测试资产：opencv-mobile-2.4.13.7-android.zip（真实 release asset）
ASSET = "https://github.com/nihui/opencv-mobile/releases/download/v36/opencv-mobile-2.4.13.7-android.zip"

proxies = [
    ("direct",                    ASSET),
    ("ghproxy.net",              "https://ghproxy.net/" + ASSET),
    ("ghproxy.com",              "https://ghproxy.com/" + ASSET),
    ("github.moeyy.xyz",         "https://github.moeyy.xyz/" + ASSET),
    ("ghproxy.net (no-slash)",   "https://ghproxy.net/" + ASSET),
]

# JDK 实际二进制（adoptium API 302 到真实文件）
JDK = "https://api.adoptium.net/v3/binary/latest/11/ga/windows/x64/jdk/hotspot/normal/eclipse"

def range_get(label, url, n=2048):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={**UA, 'Range': 'bytes=0-%d' % (n-1)})
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read()
            return "%-22s OK  status=%s bytes=%d  %.1fs" % (label, r.status, len(data), time.time()-t0)
    except urllib.error.HTTPError as e:
        return "%-22s HTTP %s  %.1fs" % (label, e.code, time.time()-t0)
    except Exception as e:
        return "%-22s ERR  %s  %.1fs" % (label, repr(e)[:70], time.time()-t0)

print("=== GitHub asset via proxies (expect bytes>0) ===")
for label, url in proxies:
    print(range_get(label, url), flush=True)

print("=== JDK via adoptium API (302 redirect) ===")
print(range_get("adoptium JDK", JDK), flush=True)
