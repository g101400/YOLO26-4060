# -*- coding: utf-8 -*-
"""YOLOv5-Lite 推理封装（ncnn）。

前处理 / 后处理与安卓端 jni/yolov5.cpp 严格对齐：
    - letterbox：长边缩到 target_size，短边等比，右侧与下方补 114
    - 归一化：x / 255
    - 输入 blob：images；输出 blob：output(8) / 1111(16) / 2222(32)
    - 解码：sigmoid + anchor，NMS 后按 scale 还原到原图坐标并裁剪到画幅内

模型文件直接复用安卓 assets 里的 .param / .bin，无需重新导出。
"""
import os

import cv2
import numpy as np
import ncnn

# (stride, 输出 blob 名, 该层的 3 组 anchor)
HEADS = (
    (8,  "output", ((10., 13.), (16., 30.), (33., 23.))),
    (16, "1111",   ((30., 61.), (62., 45.), (59., 119.))),
    (32, "2222",   ((116., 90.), (156., 198.), (373., 326.))),
)

# anchor-free 系列（YOLOv8 / YOLO11 / YOLO26）在 ncnn 下的统一形状，见 P1 实测：
# ultralytics 导出会把 DFL / anchor 网格 / stride 缩放 / sigmoid 全部烘焙进图，
# 端上拿到的 out0 就是 (84, N)：行 0-3 = cx,cy,w,h（输入尺寸的绝对像素），行 4-83 = 80 类概率（已 sigmoid）。
# 因此三个系列**共用同一套解码**，无需在端上实现 DFL softmax。
ANCHORFREE_IN = "in0"
ANCHORFREE_OUT = "out0"

# 与安卓端 spinner 顺序一致：(显示名, 模型前缀, 输入尺寸, 系列)
# 系列决定：输入/输出 blob 名、letterbox 补边方式、解码方式
MODELS = (
    ("320-lite-e（最快）",   "e",   320, "v5lite"),
    ("416-lite-e",           "e",   416, "v5lite"),
    ("320-lite-i8e（量化）", "i8e", 320, "v5lite"),
    ("416-lite-i8e（量化）", "i8e", 416, "v5lite"),
    ("416-lite-s（推荐）",   "s",   416, "v5lite"),
    ("416-lite-i8s（量化）", "i8s", 416, "v5lite"),
    ("512-lite-c（最准）",   "c",   512, "v5lite"),
    ("YOLOv8n 320（推荐）",  "yolov8n_320", 320, "anchorfree"),
    ("YOLOv8n 416",          "yolov8n_416", 416, "anchorfree"),
    ("YOLOv8n 640（最准）",  "yolov8n_640", 640, "anchorfree"),
)

DEFAULT_MODEL_INDEX = 4      # 416-lite-s，与安卓默认一致


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


class Detector(object):
    def __init__(self, model_dir):
        self.model_dir = model_dir
        self.net = None
        self.target_size = 416
        self.model_key = None
        self.series = "v5lite"

    def load(self, model_index=DEFAULT_MODEL_INDEX):
        name, key, size, series = MODELS[model_index]
        param = os.path.join(self.model_dir, key + ".param")
        model = os.path.join(self.model_dir, key + ".bin")
        if not (os.path.isfile(param) and os.path.isfile(model)):
            raise IOError("模型文件缺失：%s / %s" % (param, model))

        net = ncnn.Net()
        net.opt.num_threads = max(1, (os.cpu_count() or 4))
        if net.load_param(param) != 0:
            raise IOError("load_param 失败：%s" % param)
        if net.load_model(model) != 0:
            raise IOError("load_model 失败：%s" % model)

        self.net = net
        self.target_size = size
        self.model_key = key
        self.series = series
        return name

    @property
    def loaded(self):
        return self.net is not None

    def detect(self, bgr, prob_threshold=0.60, nms_threshold=0.60):
        """返回 [(x0, y0, x1, y1, label, prob), ...]，坐标为原图像素。"""
        if not self.loaded:
            raise RuntimeError("模型未加载")

        img_h, img_w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        if self.series == "anchorfree":
            # ultralytics letterbox：等比缩放后【居中】补边（与导出时的前处理一致，
            # 用 v5lite 那种右下补边会导致框整体偏移）
            scale = min(float(self.target_size) / img_w, float(self.target_size) / img_h)
            nw = max(1, int(round(img_w * scale)))
            nh = max(1, int(round(img_h * scale)))
            left = (self.target_size - nw) // 2
            top = (self.target_size - nh) // 2
            pad_x, pad_y = float(left), float(top)
            resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)
            padded = cv2.copyMakeBorder(resized, top, self.target_size - nh - top,
                                        left, self.target_size - nw - left,
                                        cv2.BORDER_CONSTANT, value=(114, 114, 114))
        else:
            # letterbox（与 C++ 一致：长边缩到 target_size，短边按 int 截断，右下补边）
            pad_x, pad_y = 0.0, 0.0
            if img_w > img_h:
                scale = float(self.target_size) / img_w
                w, h = self.target_size, int(img_h * scale)
            else:
                scale = float(self.target_size) / img_h
                h, w = self.target_size, int(img_w * scale)
            w, h = max(1, w), max(1, h)

            resized = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)
            padded = cv2.copyMakeBorder(resized, 0, self.target_size - h, 0, self.target_size - w,
                                        cv2.BORDER_CONSTANT, value=(114, 114, 114))

        mat = ncnn.Mat.from_pixels(padded.tobytes(),
                                   ncnn.Mat.PixelType.PIXEL_RGB,
                                   self.target_size, self.target_size)
        # ncnn 的 Python 绑定要求两个参数都是序列（不能传 int 0）
        mat.substract_mean_normalize([0., 0., 0.], [1 / 255., 1 / 255., 1 / 255.])

        ex = self.net.create_extractor()
        boxes, scores, labels = [], [], []

        if self.series == "anchorfree":
            ex.input(ANCHORFREE_IN, mat)
            ret, out = ex.extract(ANCHORFREE_OUT)
            if ret != 0:
                return []
            arr = self._as_chw(out)
            if arr is None:
                return []
            self._decode_anchorfree(arr, self.target_size, prob_threshold,
                                    boxes, scores, labels)
        else:
            ex.input("images", mat)
            for stride, blob, anchors in HEADS:
                ret, out = ex.extract(blob)
                if ret != 0:
                    continue
                arr = self._as_chw(out)
                if arr is None:
                    continue
                self._decode(arr, stride, anchors, self.target_size, prob_threshold,
                             boxes, scores, labels)

        if not boxes:
            return []

        boxes = np.asarray(boxes, dtype=np.float32)
        scores = np.asarray(scores, dtype=np.float32)
        labels = np.asarray(labels, dtype=np.int32)

        picked = self._nms(boxes, scores, nms_threshold)

        # 逆变换回原图坐标：
        #   v5lite     —— 右下补边，无偏移，(x / scale) 即可
        #   anchorfree —— 居中补边，需先减 pad 再除 scale
        results = []
        for i in picked:
            x0, y0, x1, y1 = boxes[i]
            x0 = (x0 - pad_x) / scale
            y0 = (y0 - pad_y) / scale
            x1 = (x1 - pad_x) / scale
            y1 = (y1 - pad_y) / scale
            results.append((float(min(max(x0, 0.0), img_w - 1)),
                            float(min(max(y0, 0.0), img_h - 1)),
                            float(min(max(x1, 0.0), img_w - 1)),
                            float(min(max(y1, 0.0), img_h - 1)),
                            int(labels[i]), float(scores[i])))
        return results

    @staticmethod
    def _as_chw(mat):
        """ncnn.Mat → (c, h, w) 的 float 数组，兼容不同绑定版本的排布。"""
        try:
            arr = mat.numpy()
        except Exception:
            return None
        arr = np.asarray(arr)
        # anchor-free 系列的输出是二维 (84, N)：行=通道，列=anchor 数。
        # 原实现要求 ndim==3，会把这种输出误判为 None 并静默返回空结果，必须放行。
        if arr.ndim == 2:
            return arr
        if arr.ndim != 3:
            return None
        if arr.shape[0] == 3 and arr.shape[2] >= 85:
            return arr
        if arr.shape[2] == 3 and arr.shape[1] >= 85:
            return np.transpose(arr, (2, 0, 1))
        return arr.reshape(mat.c, mat.h, mat.w)

    @staticmethod
    def _decode(arr, stride, anchors, target_size, prob_threshold, boxes, scores, labels):
        """arr: (3, num_grid, 85)"""
        ng = target_size // stride
        for q in range(arr.shape[0]):
            feat = arr[q]                       # (num_grid, 85)
            if feat.shape[1] < 6:
                continue
            box_score = feat[:, 4]
            cls_scores = feat[:, 5:]
            class_index = cls_scores.argmax(axis=1)
            class_score = cls_scores[np.arange(feat.shape[0]), class_index]
            conf = _sigmoid(box_score) * _sigmoid(class_score)

            idx = np.nonzero(conf >= prob_threshold)[0]
            if idx.size == 0:
                continue

            j = (idx % ng).astype(np.float32)
            i = (idx // ng).astype(np.float32)
            dx, dy = _sigmoid(feat[idx, 0]), _sigmoid(feat[idx, 1])
            dw, dh = _sigmoid(feat[idx, 2]), _sigmoid(feat[idx, 3])

            aw, ah = anchors[q]
            cx = (dx * 2.0 - 0.5 + j) * stride
            cy = (dy * 2.0 - 0.5 + i) * stride
            bw = (dw * 2.0) ** 2 * aw
            bh = (dh * 2.0) ** 2 * ah

            for k in range(idx.size):
                boxes.append((cx[k] - bw[k] * 0.5, cy[k] - bh[k] * 0.5,
                              cx[k] + bw[k] * 0.5, cy[k] + bh[k] * 0.5))
                scores.append(float(conf[idx[k]]))
                labels.append(int(class_index[idx[k]]))

    @staticmethod
    def _decode_anchorfree(arr, target_size, prob_threshold, boxes, scores, labels):
        """YOLOv8 / YOLO11 / YOLO26 通用解码。

        arr: (84, N)
            行 0-3  = cx, cy, w, h（已是 target_size 空间的绝对像素，无需再乘 stride）
            行 4-83 = 80 类概率（导出时已做 sigmoid，直接与阈值比较即可）

        ⚠️ 这三条是 ultralytics 8.4.x ncnn 导出的实测结论：DFL / anchor 网格 /
        stride 缩放 / sigmoid 全部被烘焙进计算图，端上**不要**再做 DFL softmax。
        """
        # 84 = 4(cx,cy,w,h) + 80(COCO 类)。⚠️ 曾误写成要求 >=85，导致恒为空结果。
        if arr.ndim != 2 or arr.shape[0] <= 4:
            return
        n_cls = arr.shape[0] - 4
        cls = arr[4:, :]                    # (80, N)
        score = cls.max(axis=0)
        label = cls.argmax(axis=0)
        keep = score > prob_threshold
        if not keep.any():
            return
        cx = arr[0][keep]
        cy = arr[1][keep]
        bw = arr[2][keep]
        bh = arr[3][keep]
        boxes.extend(np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1).tolist())
        scores.extend(score[keep].tolist())
        labels.extend(label[keep].tolist())

    @staticmethod
    def _nms(boxes, scores, threshold):
        x0, y0, x1, y1 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = np.maximum(0, x1 - x0) * np.maximum(0, y1 - y0)
        order = scores.argsort()[::-1]
        picked = []
        while order.size > 0:
            i = order[0]
            picked.append(i)
            rest = order[1:]
            if rest.size == 0:
                break
            xx0 = np.maximum(x0[i], x0[rest])
            yy0 = np.maximum(y0[i], y0[rest])
            xx1 = np.minimum(x1[i], x1[rest])
            yy1 = np.minimum(y1[i], y1[rest])
            inter = np.maximum(0, xx1 - xx0) * np.maximum(0, yy1 - yy0)
            union = areas[i] + areas[rest] - inter
            order = rest[np.where(union <= 0, 0, inter / union) <= threshold]
        return picked
