# -*- coding: utf-8 -*-
"""
P1 侦察 v2：实测 YOLOv8 / YOLO11 / YOLO26 的 head 输出结构
- 权重走本地缓存，不联网
- 兼容新版 ultralytics 返回 dict
- 顺带导出 ncnn，从 .param 读真实输出 blob 形状（部署端真正关心的）
"""
import os, io, json, glob, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "recon")
os.makedirs(OUT, exist_ok=True)

import torch
from ultralytics import YOLO

print("torch", torch.__version__, "| ultralytics", __import__("ultralytics").__version__)
print("=" * 70)

MODELS = [
    ("v8",  "yolov8n.pt", "2.x"),
    ("v11", "yolo11n.pt", "3.x"),
    ("v26", "yolo26n.pt", "6.x"),
]


def shapes_of(y):
    """兼容 tensor / list / dict"""
    if isinstance(y, dict):
        return {k: shapes_of(v) for k, v in y.items()}
    if isinstance(y, (list, tuple)):
        return [shapes_of(v) for v in y]
    if hasattr(y, "shape"):
        return list(y.shape)
    return str(type(y))


report = {}
for tag, w, series in MODELS:
    p = os.path.join(HERE, w)
    item = {"tag": tag, "weight": w, "series": series, "local": os.path.isfile(p)}
    if not os.path.isfile(p):
        item["error"] = "权重缺失: %s" % p
        report[tag] = item
        continue
    try:
        m = YOLO(p)
        head = m.model.model[-1]
        item["task"] = m.task
        item["head_cls"] = type(head).__name__
        item["has_dfl_module"] = getattr(head, "dfl", None) is not None
        item["reg_max"] = int(getattr(head, "reg_max", 0) or 0)
        item["nc"] = int(getattr(head, "nc", 0) or 0)
        try:
            item["strides"] = [round(float(s), 1) for s in head.stride.tolist()]
        except Exception:
            pass
        item["end2end"] = bool(getattr(head, "end2end", False))
        item["one2one"] = hasattr(head, "one2one_cv2")
        item["one2many"] = hasattr(head, "one2many_cv2")

        # 实测 forward（320 输入）
        m.model.eval()
        with torch.no_grad():
            y = m.model(torch.zeros(1, 3, 320, 320))
        item["fwd_shapes"] = shapes_of(y)

        # 解码公式判定
        C = None
        fs = item["fwd_shapes"]
        if isinstance(fs, dict):
            fs = fs.get("one2many") or fs.get("one2one") or list(fs.values())[0]
        if isinstance(fs, list) and fs and isinstance(fs[0], list):
            C = fs[0][1] if len(fs[0]) > 1 else None
        item["C"] = C
        nm, reg, nc = item["nc"], item["reg_max"], item["nc"]
        if C is not None:
            if reg > 1 and C == 4 * reg + nc:
                item["formula"] = "DFL: C = 4*reg_max(%d) + nc(%d) = %d  → 需 16-bin softmax 加权" % (reg, nc, C)
            elif reg == 1 and C == 4 + nc:
                item["formula"] = "无DFL(退化): C = 4*1 + nc(%d) = %d  → 直接取 4 值，无需 softmax" % (nc, C)
            else:
                item["formula"] = "未匹配: C=%d reg_max=%d nc=%d" % (C, reg, nc)
    except Exception as e:
        item["error"] = "%s: %s" % (type(e).__name__, e)
    report[tag] = item
    print(json.dumps(item, ensure_ascii=False, indent=2))
    print("-" * 70)

with io.open(os.path.join(OUT, "head_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== 汇总：决定解码公式的关键数字 ===")
for t in ("v8", "v11", "v26"):
    it = report.get(t, {})
    if "C" in it and it["C"]:
        print("%-4s reg_max=%-3s nc=%-3s C=%-4d strides=%s" % (t, it.get("reg_max"), it.get("nc"), it["C"], it.get("strides")))
        print("      %s" % it.get("formula"))
        print("      end2end=%s one2one=%s one2many=%s" % (it.get("end2end"), it.get("one2one"), it.get("one2many")))
    else:
        print("%-4s ERROR %s" % (t, it.get("error")))
