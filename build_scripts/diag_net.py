# 网络可达性诊断：本环境代理对哪些 host 放行
import urllib.request, ssl, time

UA = {'User-Agent': 'Mozilla/5.0'}

# (label, url) — 用 HEAD/小 GET 探测，不下载大文件
tests = [
    ("github.com",               "https://github.com"),
    ("github releases CDN",      "https://objects.githubusercontent.com"),
    ("raw.githubusercontent",     "https://raw.githubusercontent.com"),
    ("api.github.com",           "https://api.github.com"),
    ("api.adoptium.net",         "https://api.adoptium.net/v3/info/available_releases"),
    ("dl.google.com",            "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"),
    ("maven.google.com",         "https://maven.google.com"),
    ("repo1.maven.org",          "https://repo1.maven.org/maven2/"),
    ("mirrors.cloud.tencent.com","https://mirrors.cloud.tencent.com"),
    ("mirrors.tuna.tsinghua",    "https://mirrors.tuna.tsinghua.edu.cn"),
    ("ghproxy.net",              "https://ghproxy.net/https://github.com"),
    ("mirror.ghproxy.com",       "https://mirror.ghproxy.com/https://github.com"),
    ("services.gradle.org",      "https://services.gradle.org/distributions/gradle-5.4.1-all.zip"),
]

def probe(label, url):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=UA, method='HEAD')
        with urllib.request.urlopen(req, timeout=20) as r:
            return "%-26s OK  %s  %s" % (label, r.status, "%.1fs" % (time.time()-t0))
    except urllib.error.HTTPError as e:
        return "%-26s HTTP %s  %.1fs" % (label, e.code, time.time()-t0)
    except Exception as e:
        return "%-26s ERR  %s  %.1fs" % (label, repr(e)[:60], time.time()-t0)

for label, url in tests:
    print(probe(label, url), flush=True)
