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

#ifndef YOLOv8_H
#define YOLOv8_H

#include <opencv2/core/core.hpp>

#include <net.h>

struct Object
{
    cv::Rect_<float> rect;
    int label;
    float prob;
    float box_score;
    float unsig_pro;
};


class Yolov8
{
public:
    Yolov8();

    // 文件方式加载（桌面/调试用）
    int load(const char* modeltype, int target_size, const float* mean_vals, const float* norm_vals, bool use_gpu = false);

    // Asset 方式加载（安卓 APK 内打包模型）
    int load(AAssetManager* mgr, const char* modeltype, int target_size, bool use_gpu = false);

    // anchor-free 解码：in0 -> out0，out 形状 (84, N)
    int detect(const cv::Mat& rgb, std::vector<Object>& objects, float prob_threshold = 0.60f, float nms_threshold = 0.60f);

    // 绘制（安卓端实际由 Java 层用系统字体画中文标签，此处保留备用）
    int draw(cv::Mat& rgb, const std::vector<Object>& objects);

private:

    ncnn::Net yolov8;

    int target_size;
    float mean_vals[3];
    float norm_vals[3];
    int image_w;
    int image_h;
    int in_w;
    int in_h;

    ncnn::UnlockedPoolAllocator blob_pool_allocator;
    ncnn::PoolAllocator workspace_pool_allocator;
};

#endif // YOLOv8_H
