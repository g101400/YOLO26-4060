# -*- coding: utf-8 -*-
"""
P1 决定性验证：ncnn 输出 out0 的语义到底是什么
对照 ultralytics PyTorch 官方预测结果，判定：
  A) 行 0..3 是 l,t,r,b（距 anchor 的四边距离，已乘 stride）还是 x1,y1,x2,y2
  B) 行 4..83 是否已是 sigmoid 后的概率
  C) 三个系列（v8/v11/v26）能否用同一个解码器
"""
import os, io, json
import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "zidane.jpg")
IMGSZ = 320
STRIDES = [8, 16, 32]

import ncnn


def letterbox(im, size=320, color=114):
    h, w = im.shape[:2]
    r = min(size / h, size / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    im2 = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_LINEAR)
    top = (size - nh) // 2
    bottom = size - nh - top
    left = (size - nw) // 2
    right = size - nw - left
    out = cv2.copyMakeBorder(im2, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(color, color, color))
    return out, r, (left, top)


def nms(boxes, scores, thr=0.45):
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        order = order[1:][iou <= thr]
    return keep


def decode(mode, out, r, pad, conf=0.25):
    """mode: 'ltrb' 或 'xyxy'"""
    C, N = out.shape
    boxes4 = out[0:4, :].T          # (N,4)
    cls = out[4:, :].T              # (N,80)
    # anchor 网格中心
    pts = []
    for s in STRIDES:
        g = IMGSZ // s
        yy, xx = np.meshgrid(np.arange(g), np.arange(g), indexing="ij")
        pts.append(np.stack([(xx + 0.5) * s, (yy + 0.5) * s], -1).reshape(-1, 2))
    pts = np.concatenate(pts, 0)    # (2100,2)
    if mode == "ltrb":
        x1 = pts[:, 0:1] - boxes4[:, 0:1]
        y1 = pts[:, 1:2] - boxes4[:, 1:2]
        x2 = pts[:, 0:1] + boxes4[:, 2:3]
        y2 = pts[:, 1:2] + boxes4[:, 3:4]
    elif mode == "cxcywh":
        cx, cy, bw, bh = boxes4[:, 0:1], boxes4[:, 1:2], boxes4[:, 2:3], boxes4[:, 3:4]
        x1, y1, x2, y2 = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2
    else:
        x1, y1, x2, y2 = boxes4[:, 0:1], boxes4[:, 1:2], boxes4[:, 2:3], boxes4[:, 3:4]
    cls_max = cls.max(1)
    lbl = cls.argmax(1)
    m = cls_max > conf
    if not m.any():
        return []
    b = np.concatenate([x1, y1, x2, y2], 1)[m]
    sc = cls_max[m]
    lb = lbl[m]
    keep = nms(b, sc)
    res = []
    for i in keep:
        bx = b[i].copy()
        bx[[0, 2]] = (bx[[0, 2]] - pad[0]) / r
        bx[[1, 3]] = (bx[[1, 3]] - pad[1]) / r
        res.append({"cls": int(lb[i]), "score": round(float(sc[i]), 3),
                    "xyxy": [round(float(v), 1) for v in bx]})
    return res


def run_ncnn(d):
    im = cv2.imread(IMG)
    lb, r, pad = letterbox(im, IMGSZ)
    mat = ncnn.Mat.from_pixels(lb.tobytes(), ncnn.Mat.PixelType.PIXEL_BGR2RGB, IMGSZ, IMGSZ)
    mat.substract_mean_normalize([], [1 / 255.0, 1 / 255.0, 1 / 255.0])
    net = ncnn.Net()
    net.opt.use_vulkan_compute = False
    net.load_param(os.path.join(d, "model.ncnn.param"))
    net.load_model(os.path.join(d, "model.ncnn.bin"))
    with net.create_extractor() as ex:
        ex.input("in0", mat)
        _, o = ex.extract("out0")
    return np.array(o), r, pad


print("图:", os.path.basename(IMG), " imgsz=", IMGSZ)
print("=" * 76)

# 基准：ultralytics PyTorch
from ultralytics import YOLO
COCO = ["person", "bicycle", "car", "motorbike", "aeroplane", "bus", "train", "truck", "boat",
        "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
        "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
        "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
        "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
        "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
        "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "sofa",
        "pottedplant", "bed", "diningtable", "toilet", "tvmonitor", "laptop", "mouse", "remote",
        "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
        "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"]

report = {}
for tag, w, d in [("v8", "yolov8n.pt", "yolov8n_ncnn_model"),
                  ("v11", "yolo11n.pt", "yolo11n_ncnn_model"),
                  ("v26", "yolo26n.pt", "yolo26n_ncnn_model")]:
    item = {}
    out, r, pad = run_ncnn(d)
    item["out_shape"] = list(out.shape)
    item["box4_range"] = [round(float(out[0:4].min()), 2), round(float(out[0:4].max()), 2)]
    item["cls_range"] = [round(float(out[4:].min()), 4), round(float(out[4:].max()), 4)]
    item["decode_ltrb"] = decode("ltrb", out, r, pad)
    item["decode_xyxy"] = decode("xyxy", out, r, pad)
    item["decode_cxcywh"] = decode("cxcywh", out, r, pad)

    # PyTorch 基准
    m = YOLO(os.path.join(HERE, w))
    res = m.predict(IMG, imgsz=IMGSZ, conf=0.25, verbose=False)[0]
    base = []
    for b in res.boxes:
        base.append({"cls": int(b.cls[0]), "score": round(float(b.conf[0]), 3),
                     "xyxy": [round(float(v), 1) for v in b.xyxy[0].tolist()]})
    item["torch_baseline"] = base
    report[tag] = item

    def fmt(lst):
        return "; ".join("%s %.2f [%s]" % (COCO[x["cls"]], x["score"],
                                           ",".join(str(v) for v in x["xyxy"])) for x in lst[:4]) or "(无)"

    print("\n### %s  out0=%s" % (tag, item["out_shape"]))
    print("   box4 值域: %s   cls 值域: %s  (cls 若在 0..1 → 已 sigmoid)" % (item["box4_range"], item["cls_range"]))
    print("   PyTorch基准 : %s" % fmt(base))
    print("   解码ltrb    : %s" % fmt(item["decode_ltrb"]))
    print("   解码xyxy    : %s" % fmt(item["decode_xyxy"]))
    print("   解码cxcywh  : %s   <<<" % fmt(item["decode_cxcywh"]))

with io.open(os.path.join(HERE, "recon", "decode_verify.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 76)
print("结论提示：与 PyTorch 基准行数/坐标最接近的那种解码方式即为正确语义")
