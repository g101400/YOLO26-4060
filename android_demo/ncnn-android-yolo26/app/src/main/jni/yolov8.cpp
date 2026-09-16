// Tencent is pleased to support the open source community by making ncnn available.
//
// Copyright (C) 2021 THL A29 Limited, a Tencent company. All rights reserved.
//
// Licensed under the BSD 3-Clause License (the "License"); you may not use this file except
// in compliance with the License. You may obtain a copy of the License at
//
// https://opensource.org/licenses/BSD-3-Clause
//
// Unless required by applicable law or agreed to in writing, software distributed
// under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
// CONDITIONS OF ANY KIND, either express or implied. See the License for the
// specific language governing permissions and limitations under the License.

// YOLOv8 / YOLO11 / YOLO26 anchor-free 解码器（ncnn 安卓端）。
// 与桌面端 detector.py::_decode_anchorfree 严格对齐（同一套 ncnn 导出）。
// 输入 blob: in0；输出 blob: out0；out 形状 (84, N)：
//   out.row(0..3) = cx, cy, w, h（已是 target_size 空间的绝对像素）
//   out.row(4..83) = 80 类概率（导出时已做 sigmoid，直接与阈值比较）
// DFL / anchor 网格 / stride 缩放全部被烘焙进计算图，端上不要再 sigmoid 之外的处理。

#include "yolov8.h"
#include <benchmark.h>
#include <opencv2/core/core.hpp>
#include <opencv2/imgproc/imgproc.hpp>

#include "omp.h"
#include "cpu.h"


static inline float intersection_area(const Object &a, const Object &b) {
    cv::Rect_<float> inter = a.rect & b.rect;
    return inter.area();
}

static void qsort_descent_inplace(std::vector<Object> &faceobjects, int left, int right) {
    int i = left;
    int j = right;
    float p = faceobjects[(left + right) / 2].prob;

    while (i <= j) {
        while (faceobjects[i].prob > p)
            i++;

        while (faceobjects[j].prob < p)
            j--;

        if (i <= j) {
            // swap
            std::swap(faceobjects[i], faceobjects[j]);

            i++;
            j--;
        }
    }

#pragma omp parallel sections
    {
#pragma omp section
        {
            if (left < j) qsort_descent_inplace(faceobjects, left, j);
        }
#pragma omp section
        {
            if (i < right) qsort_descent_inplace(faceobjects, i, right);
        }
    }
}

static void qsort_descent_inplace(std::vector<Object> &faceobjects) {
    if (faceobjects.empty())
        return;

    qsort_descent_inplace(faceobjects, 0, faceobjects.size() - 1);
}

static void nms_sorted_bboxes(const std::vector<Object> &faceobjects, std::vector<int> &picked,
                              float nms_threshold) {
    picked.clear();

    const int n = faceobjects.size();

    std::vector<float> areas(n);
    for (int i = 0; i < n; i++) {
        areas[i] = faceobjects[i].rect.area();
    }

    for (int i = 0; i < n; i++) {
        const Object &a = faceobjects[i];

        int keep = 1;
        for (int j = 0; j < (int) picked.size(); j++) {
            const Object &b = faceobjects[picked[j]];

            // intersection over union
            float inter_area = intersection_area(a, b);
            float union_area = areas[i] + areas[picked[j]] - inter_area;
            // float IoU = inter_area / union_area
            if (inter_area / union_area > nms_threshold)
                keep = 0;
        }

        if (keep)
            picked.push_back(i);
    }
}

// out 已确认：c=1, h=84, w=N(anchor 数)。out.row(r) 第 r 行即第 r 通道。
// 返回每行首地址，便于内层循环逐 anchor 取数。
static inline const float* row_ptr(const ncnn::Mat& m, int r) {
    return m.row(r);
}


Yolov8::Yolov8() {
    blob_pool_allocator.set_size_compare_ratio(0.f);
    workspace_pool_allocator.set_size_compare_ratio(0.f);
}

int Yolov8::load(const char *modeltype, int _target_size, const float *_mean_vals,
                 const float *_norm_vals, bool use_gpu) {
    yolov8.clear();
    blob_pool_allocator.clear();
    workspace_pool_allocator.clear();

    ncnn::set_cpu_powersave(2);
    ncnn::set_omp_num_threads(ncnn::get_big_cpu_count());

    yolov8.opt = ncnn::Option();

#if NCNN_VULKAN
    yolov8.opt.use_vulkan_compute = use_gpu;
#endif
    yolov8.opt.num_threads = ncnn::get_big_cpu_count();
    yolov8.opt.blob_allocator = &blob_pool_allocator;
    yolov8.opt.workspace_allocator = &workspace_pool_allocator;

    char parampath[256];
    char modelpath[256];
    sprintf(parampath, "%s.param", modeltype);
    sprintf(modelpath, "%s.bin", modeltype);

    yolov8.load_param(parampath);
    yolov8.load_model(modelpath);

    target_size = _target_size;

    mean_vals[0] = 0.f;
    mean_vals[1] = 0.f;
    mean_vals[2] = 0.f;
    norm_vals[0] = 1.f / 255.f;
    norm_vals[1] = 1.f / 255.f;
    norm_vals[2] = 1.f / 255.f;

    return 0;
}

int Yolov8::load(AAssetManager *mgr, const char *modeltype, int _target_size, bool use_gpu) {
    yolov8.clear();
    blob_pool_allocator.clear();
    workspace_pool_allocator.clear();

    ncnn::set_cpu_powersave(2);
    ncnn::set_omp_num_threads(ncnn::get_big_cpu_count());

    yolov8.opt = ncnn::Option();
#if NCNN_VULKAN
    yolov8.opt.use_vulkan_compute = use_gpu;
#endif
    yolov8.opt.num_threads = ncnn::get_big_cpu_count();
    yolov8.opt.blob_allocator = &blob_pool_allocator;
    yolov8.opt.workspace_allocator = &workspace_pool_allocator;

    target_size = _target_size;

    char parampath[256];
    char modelpath[256];
    sprintf(parampath, "%s.param", modeltype);
    sprintf(modelpath, "%s.bin", modeltype);

    yolov8.load_param(mgr, parampath);
    yolov8.load_model(mgr, modelpath);

    return 0;
}


int Yolov8::detect(const cv::Mat &rgb, std::vector<Object> &objects, float prob_threshold,
                   float nms_threshold) {
    int img_w = rgb.cols;
    int img_h = rgb.rows;

    // ultralytics letterbox：长边缩到 target_size，等比缩放后【居中】补边
    // （与导出时前处理一致；右下补边会让框整体偏移）
    float scale = std::min((float) target_size / img_w, (float) target_size / img_h);
    int w = (int) (img_w * scale);
    int h = (int) (img_h * scale);
    if (w < 1) w = 1;
    if (h < 1) h = 1;

    int wpad = target_size - w;
    int hpad = target_size - h;
    int left = wpad / 2;
    int top = hpad / 2;
    int right = wpad - left;
    int bottom = hpad - top;

    ncnn::Mat in = ncnn::Mat::from_pixels_resize(rgb.data, ncnn::Mat::PIXEL_RGB, img_w, img_h,
                                                 w, h);

    // 居中补边到 target_size × target_size
    ncnn::Mat in_pad;
    ncnn::copy_make_border(in, in_pad, top, bottom, left, right, ncnn::BORDER_CONSTANT, 114.f);

    const float norm_vals[3] = {1 / 255.f, 1 / 255.f, 1 / 255.f};
    in_pad.substract_mean_normalize(0, norm_vals);

    ncnn::Extractor ex = yolov8.create_extractor();

    ex.input("in0", in_pad);

    ncnn::Mat out;
    ex.extract("out0", out);          // out.c=1, out.h=84, out.w=N

    const int num_class = 80;
    const int num_anchors = out.w;

    const float *pcx = row_ptr(out, 0);
    const float *pcy = row_ptr(out, 1);
    const float *pw  = row_ptr(out, 2);
    const float *ph  = row_ptr(out, 3);

    // 预存每个类通道的首地址，避免内层循环反复取行
    std::vector<const float*> pcls(num_class);
    for (int c = 0; c < num_class; c++)
        pcls[c] = row_ptr(out, 4 + c);

    std::vector<Object> proposals;
    proposals.reserve(num_anchors);

    for (int i = 0; i < num_anchors; i++) {
        // 80 类中取最大分数（已 sigmoid），同时记录类别
        float best = 0.f;
        int best_label = 0;
        for (int c = 0; c < num_class; c++) {
            float s = pcls[c][i];
            if (s > best) {
                best = s;
                best_label = c;
            }
        }

        if (best > prob_threshold) {
            float bx = pcx[i];
            float by = pcy[i];
            float bw = pw[i];
            float bh = ph[i];

            Object obj;
            obj.rect.x = bx - bw * 0.5f;
            obj.rect.y = by - bh * 0.5f;
            obj.rect.width = bw;
            obj.rect.height = bh;
            obj.label = best_label;
            obj.prob = best;
            obj.box_score = 0.f;
            obj.unsig_pro = 0.f;

            proposals.push_back(obj);
        }
    }

    qsort_descent_inplace(proposals);

    // apply nms with nms_threshold（proposals 已按 prob 降序）
    std::vector<int> picked;
    nms_sorted_bboxes(proposals, picked, nms_threshold);

    int count = picked.size();

    objects.resize(count);
#pragma omp parallel for num_threads(ncnn::get_big_cpu_count())
    for (int i = 0; i < count; i++) {
        objects[i] = proposals[picked[i]];

        // 逆变换回原图坐标：先减居中补边，再除 scale
        float x0 = (objects[i].rect.x - left) / scale;
        float y0 = (objects[i].rect.y - top) / scale;
        float x1 = (objects[i].rect.x + objects[i].rect.width - left) / scale;
        float y1 = (objects[i].rect.y + objects[i].rect.height - top) / scale;

        // clip
        x0 = std::max(std::min(x0, (float) (img_w - 1)), 0.f);
        y0 = std::max(std::min(y0, (float) (img_h - 1)), 0.f);
        x1 = std::max(std::min(x1, (float) (img_w - 1)), 0.f);
        y1 = std::max(std::min(y1, (float) (img_h - 1)), 0.f);

        objects[i].rect.x = x0;
        objects[i].rect.y = y0;
        objects[i].rect.width = x1 - x0;
        objects[i].rect.height = y1 - y0;
    }

    struct {
        bool operator()(const Object &a, const Object &b) const {
            return a.rect.area() > b.rect.area();
        }
    } objects_area_greater;
    std::sort(objects.begin(), objects.end(), objects_area_greater);

    return 0;
}

int Yolov8::draw(cv::Mat &rgb, const std::vector<Object> &objects) {
    static const char *class_names[] = {
            "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
            "boat",
            "traffic light",
            "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
            "horse",
            "sheep", "cow",
            "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie",
            "suitcase", "frisbee",
            "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
            "skateboard", "surfboard",
            "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl",
            "banana", "apple",
            "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
            "chair", "couch",
            "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
            "keyboard", "cell phone",
            "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
            "scissors", "teddy bear",
            "hair drier", "toothbrush"
    };
    static const unsigned char colors[19][3] = {
            {54,  67,  244},
            {99,  30,  233},
            {176, 39,  156},
            {183, 58,  103},
            {181, 81,  63},
            {243, 150, 33},
            {244, 169, 3},
            {212, 188, 0},
            {136, 150, 0},
            {80,  175, 76},
            {74,  195, 139},
            {57,  220, 205},
            {59,  235, 255},
            {7,   193, 255},
            {0,   152, 255},
            {34,  87,  255},
            {72,  85,  121},
            {158, 158, 158},
            {139, 125, 96}
    };

    int color_index = 0;
    #pragma omp parallel for num_threads(ncnn::get_big_cpu_count())
    for (size_t i = 0; i < objects.size(); i++) {
        const Object &obj = objects[i];

        const unsigned char *color = colors[color_index % 19];
        color_index++;

        cv::Scalar cc(color[0], color[1], color[2]);

        cv::rectangle(rgb, obj.rect, cc, 2);

        char text[256];
        sprintf(text, "%s %.1f%%", class_names[obj.label], obj.prob * 100);

        int baseLine = 0;
        cv::Size label_size = cv::getTextSize(text, cv::FONT_HERSHEY_SIMPLEX, 0.5, 1,
                                              &baseLine);

        int x = obj.rect.x;
        int y = obj.rect.y - label_size.height - baseLine;
        if (y < 0)
            y = 0;
        if (x + label_size.width > rgb.cols)
            x = rgb.cols - label_size.width;

        cv::rectangle(rgb, cv::Rect(cv::Point(x, y),
                                    cv::Size(label_size.width, label_size.height + baseLine)),
                      cc, -1);
        cv::Scalar textcc = (color[0] + color[1] + color[2] >= 381) ? cv::Scalar(0, 0, 0)
                                                                    : cv::Scalar(255, 255, 255);

        cv::putText(rgb, text, cv::Point(x, y + label_size.height),
                    cv::FONT_HERSHEY_SIMPLEX,
                    0.5,
                    textcc, 1);
    }

    return 0;
}
