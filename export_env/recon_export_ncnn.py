# -*- coding: utf-8 -*-
"""
P1 侦察 v3：把 v8 / v11 / v26 导出为 ncnn，从 .param 读真实输出 blob 形状
（部署端真正关心的是 ncnn 的 out0，不是 PyTorch 的输出）
"""
import os, io, json, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "recon")
os.makedirs(OUT, exist_ok=True)

from ultralytics import YOLO

IMGSZ = int(sys.argv[1]) if len(sys.argv) > 1 else 320
MODELS = [("v8", "yolov8n.pt"), ("v11", "yolo11n.pt"), ("v26", "yolo26n.pt")]


def parse_param_outputs(param_path):
    """从 ncnn .param 里读出所有输出 blob 的名字与形状"""
    txt = io.open(param_path, encoding="utf-8").read()
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    n_layers = int(lines[0].split()[1])
    n_blob = int(lines[0].split()[2])
    # 统计每个 blob 被谁消费
    consumed = set()
    produced = {}
    for l in lines[2:2 + n_layers]:
        p = l.split()
        op = p[0]
        outs = [x for x in p[1:1 + int(p[-2])]] if False else None
        # 统一解析：<op> <name> <n_in> <n_out> <in...> <out...>
        try:
            name = p[1]; n_in = int(p[2]); n_out = int(p[3])
            ins = p[4:4 + n_in]; outs = p[4 + n_in:4 + n_in + n_out]
        except Exception:
            continue
        for i in ins:
            if i != "-1":
                consumed.add(i)
        for o in outs:
            produced[o] = {"op": op, "name": name}
    # 输出 blob = 产生但未被消费
    outs = [b for b in produced if b not in consumed]
    # 尝试从 memory data / Split 等推断形状；ncnn param 不直接存形状，
    # 这里改为从 model.ncnn.bin 无法推断 → 交给推理实测
    return outs, n_layers, n_blob


report = {}
for tag, w in MODELS:
    p = os.path.join(HERE, w)
    item = {"tag": tag, "weight": w}
    if not os.path.isfile(p):
        item["error"] = "缺权重"; report[tag] = item; continue
    try:
        m = YOLO(p)
        exp = m.export(format="ncnn", imgsz=IMGSZ, half=False)
        d = exp if os.path.isdir(str(exp)) else os.path.dirname(str(exp))
        item["export_dir"] = d
        item["files"] = sorted(os.listdir(d))
        pm = os.path.join(d, "model.ncnn.param")
        if os.path.isfile(pm):
            outs, nl, nb = parse_param_outputs(pm)
            item["param_outputs"] = outs
            item["param_layers"] = nl
            item["param_blobs"] = nb
            # 常见输出名
            item["out0_present"] = "out0" in outs
            # param 尾部通常有输出 blob 声明行
            tail = [l.strip() for l in io.open(pm, encoding="utf-8").read().splitlines() if l.strip()]
            item["param_tail"] = tail[-1][:120]
        # 体积
        binp = os.path.join(d, "model.ncnn.bin")
        if os.path.isfile(binp):
            item["bin_MB"] = round(os.path.getsize(binp) / 1048576.0, 2)
    except Exception as e:
        item["error"] = "%s: %s" % (type(e).__name__, e)
    report[tag] = item
    print(json.dumps(item, ensure_ascii=False, indent=2))
    print("-" * 70)

with io.open(os.path.join(OUT, "ncnn_export_report.json"), "w", encoding="utf-8") as f:
    json.dump({"imgsz": IMGSZ, "models": report}, f, ensure_ascii=False, indent=2)

print("\n=== ncnn 导出汇总 (imgsz=%d) ===" % IMGSZ)
for t in ("v8", "v11", "v26"):
    it = report.get(t, {})
    if "export_dir" in it:
        print("%-4s dir=%s" % (t, os.path.basename(it["export_dir"])))
        print("     输出blob=%s  layers=%s  bin=%.2fMB" % (it.get("param_outputs"), it.get("param_layers"), it.get("bin_MB", 0)))
    else:
        print("%-4s ERROR %s" % (t, it.get("error")))
