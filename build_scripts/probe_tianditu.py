# 实测天地图瓦片接口可达性 + 校验坐标换算
import os, math, urllib.request

TILE = 256
def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n)
    return x, y

# 天安门广场
lat, lng, z = 39.9087, 116.3975, 18
x, y = lonlat_to_tile(lng, lat, z)
print('天安门 z18 中心瓦片 x=%d y=%d' % (x, y))
# 期望值参考：z18 下北京约 x=214774 y=98527 附近，可自行比对
# 取中心瓦片周边 3x3 首块做网络实测
def fetch(url, key=''):
    u = url + ('&tk=%s' % key if key else '')
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=30).read()

# 1) 无 token
url0 = 'https://t0.tianditu.gov.cn/DataServer?T=img_w&x=%d&y=%d&l=%d' % (x, y, z)
try:
    b0 = fetch(url0)
    print('无token: rc-byte=%d, magic=%r' % (len(b0), b0[:8]))
except Exception as e:
    print('无token 失败:', repr(e)[:160])

# 2) 带一个占位 token（明显无效）看返回是鉴权失败图还是 4xx
url1 = 'https://t0.tianditu.gov.cn/DataServer?T=img_w&x=%d&y=%d&l=%d' % (x, y, z)
try:
    b1 = fetch(url1, key='INVALID_DEMO_TOKEN_0000')
    print('占位token: rc-byte=%d, magic=%r' % (len(b1), b1[:8]))
except Exception as e:
    print('占位token 失败:', repr(e)[:160])
