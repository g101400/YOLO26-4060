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

#include <android/asset_manager_jni.h>
#include <android/native_window_jni.h>
#include <android/native_window.h>

#include <android/log.h>

#include <jni.h>

#include <string>
#include <vector>

#include <platform.h>
#include <benchmark.h>

#include "yolov8.h"

#include "ndkcamera.h"

#include <opencv2/core/core.hpp>
#include <opencv2/imgproc/imgproc.hpp>

#if __ARM_NEON
#include <arm_neon.h>
#endif // __ARM_NEON

static int draw_unsupported(cv::Mat& rgb)
{
    const char text[] = "unsupported";

    int baseLine = 0;
    cv::Size label_size = cv::getTextSize(text, cv::FONT_HERSHEY_SIMPLEX, 1.0, 1, &baseLine);

    int y = (rgb.rows - label_size.height) / 2;
    int x = (rgb.cols - label_size.width) / 2;

    cv::rectangle(rgb, cv::Rect(cv::Point(x, y), cv::Size(label_size.width, label_size.height + baseLine)),
                  cv::Scalar(255, 255, 255), -1);

    cv::putText(rgb, text, cv::Point(x, y + label_size.height),
                cv::FONT_HERSHEY_SIMPLEX, 1.0, cv::Scalar(0, 0, 0));

    return 0;
}

static int draw_fps(cv::Mat& rgb, double t1)
{
    double t = t1;
    // resolve moving average
    float avg_fps = 0.f;
    {
        static double t0 = 0.f;
        static float fps_history[10] = {0.f};

        double t1 = ncnn::get_current_time();
        if (t0 == 0.f)
        {
            t0 = t1;
            return 0;
        }

        float fps = 1000.f / (t1 - t0);
        t0 = t1;

        for (int i = 9; i >= 1; i--)
        {
            fps_history[i] = fps_history[i - 1];
        }
        fps_history[0] = fps;

        if (fps_history[9] == 0.f)
        {
            return 0;
        }

        for (int i = 0; i < 10; i++)
        {
            avg_fps += fps_history[i];
        }
        avg_fps /= 10.f;
    }

    char text[32];
    sprintf(text, "TIME:%.2f FPS=%.2f", t, avg_fps);

    int baseLine = 0;
    cv::Size label_size = cv::getTextSize(text, cv::FONT_HERSHEY_SIMPLEX, 0.5, 1, &baseLine);

    int y = 0;
    int x = rgb.cols - label_size.width;

    cv::rectangle(rgb, cv::Rect(cv::Point(x, y), cv::Size(label_size.width, label_size.height + baseLine)),
                  cv::Scalar(255, 255, 255), -1);

    cv::putText(rgb, text, cv::Point(x, y + label_size.height),
                cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 0, 0));

    return 0;
}

static Yolov8* g_yolov8 = 0;
static ncnn::Mutex lock;

// ---------- Java 回调：把每帧检测结果交给 Java 层（中文标签 / 状态栏 / CSV 记录） ----------
// 背景：OpenCV 的 cv::putText 只有 ASCII 字形，画不出中文（会渲染成 ???），
// 所以 native 侧只负责推理，绘制与展示全部交给 Java（OverlayView 用系统字体，含 CJK 回退）。
static JavaVM* g_vm = 0;
static jobject g_listener = 0;        // Ncnnv5lite 实例的全局引用
static jmethodID g_on_detected = 0;   // void onDetected(float[] rects, float[] probs, int[] labels)

static void report_objects(const cv::Mat& rgb, const std::vector<Object>& objects)
{
    if (!g_vm || !g_listener || !g_on_detected) return;

    // 节流：最快约 30fps 回调一次，避免高帧率场景把 UI 线程压满
    static double last_report = 0.0;
    double now = ncnn::get_current_time();
    if (last_report > 0.0 && now - last_report < 30.0) return;
    last_report = now;

    JNIEnv* env = 0;
    bool attached = false;
    if (g_vm->GetEnv((void**)&env, JNI_VERSION_1_4) != JNI_OK)
    {
        if (g_vm->AttachCurrentThread(&env, 0) != JNI_OK || !env) return;
        attached = true;
    }

    int n = (int)objects.size();
    jfloatArray jrects = env->NewFloatArray(n * 4);
    jfloatArray jprobs = env->NewFloatArray(n);
    jintArray   jlabels = env->NewIntArray(n);

    if (jrects && jprobs && jlabels)
    {
        if (n > 0)
        {
            std::vector<float> rects((size_t)n * 4);
            std::vector<float> probs((size_t)n);
            std::vector<int>   labels((size_t)n);
            float iw = rgb.cols > 0 ? (float)rgb.cols : 1.f;
            float ih = rgb.rows > 0 ? (float)rgb.rows : 1.f;
            for (int i = 0; i < n; i++)
            {
                const Object& o = objects[i];
                rects[(size_t)i * 4 + 0] = o.rect.x / iw;
                rects[(size_t)i * 4 + 1] = o.rect.y / ih;
                rects[(size_t)i * 4 + 2] = (o.rect.x + o.rect.width) / iw;
                rects[(size_t)i * 4 + 3] = (o.rect.y + o.rect.height) / ih;
                probs[(size_t)i] = o.prob;
                labels[(size_t)i] = o.label;
            }
            env->SetFloatArrayRegion(jrects, 0, n * 4, &rects[0]);
            env->SetFloatArrayRegion(jprobs, 0, n, &probs[0]);
            env->SetIntArrayRegion(jlabels, 0, n, &labels[0]);
        }
        env->CallVoidMethod(g_listener, g_on_detected, jrects, jprobs, jlabels);
    }

    if (jrects)  env->DeleteLocalRef(jrects);
    if (jprobs)  env->DeleteLocalRef(jprobs);
    if (jlabels) env->DeleteLocalRef(jlabels);

    if (attached) g_vm->DetachCurrentThread();
}

class MyNdkCamera : public NdkCameraWindow
{
public:
    virtual void on_image_render(cv::Mat& rgb) const;
};

void MyNdkCamera::on_image_render(cv::Mat& rgb) const
{
    {
        ncnn::MutexLockGuard g(lock);

        if (g_yolov8)
        {
            std::vector<Object> objects;
            g_yolov8->detect(rgb, objects);

            // 不再在 native 侧绘制：cv::putText 无中文字形（会画成 ???）。
            // 结果统一回传 Java，由 OverlayView 用系统字体画中文标签、状态栏与 CSV 记录一并处理。
            report_objects(rgb, objects);
        }
        else
        {
            draw_unsupported(rgb);
        }
    }
}

static MyNdkCamera* g_camera = 0;

extern "C" {

JNIEXPORT jint JNI_OnLoad(JavaVM* vm, void* reserved)
{
    __android_log_print(ANDROID_LOG_DEBUG, "ncnn", "JNI_OnLoad");

    g_vm = vm;

    g_camera = new MyNdkCamera;

    return JNI_VERSION_1_4;
}

JNIEXPORT void JNI_OnUnload(JavaVM* vm, void* reserved)
{
    __android_log_print(ANDROID_LOG_DEBUG, "ncnn", "JNI_OnUnload");

    if (vm && g_listener)
    {
        JNIEnv* env = 0;
        if (vm->GetEnv((void**)&env, JNI_VERSION_1_4) == JNI_OK && env)
        {
            env->DeleteGlobalRef(g_listener);
        }
        g_listener = 0;
        g_on_detected = 0;
    }

    {
        ncnn::MutexLockGuard g(lock);

        delete g_yolov8;
        g_yolov8 = 0;
    }

    delete g_camera;
    g_camera = 0;
}

// public native boolean loadModel(AssetManager mgr, int modelid, int cpugpu);
JNIEXPORT jboolean JNICALL Java_ncnn_v5lite_demo_Ncnnv5lite_loadModel(JNIEnv* env, jobject thiz, jobject assetManager, jint modelid, jint cpugpu)
{
    if (modelid < 0 || modelid > 2 || cpugpu < 0 || cpugpu > 1)
    {
        return JNI_FALSE;
    }

    AAssetManager* mgr = AAssetManager_fromJava(env, assetManager);

    __android_log_print(ANDROID_LOG_DEBUG, "ncnn", "loadModel %p", mgr);

    const char* modeltypes[] =
            {
                    "yolo26n_320",
                    "yolo26n_416",
                    "yolo26n_640",
            };


    const int target_sizes[] =
            {
                    320,
                    416,
                    640
            };


    const char* modeltype = modeltypes[(int)modelid];
    int target_size = target_sizes[(int)modelid];
    bool use_gpu = (int)cpugpu == 1;

    // reload
    {
        ncnn::MutexLockGuard g(lock);

        if (use_gpu && ncnn::get_gpu_count() == 0)
        {
            // no gpu
            delete g_yolov8;
            g_yolov8 = 0;
        }
        else
        {
            if (!g_yolov8)
                g_yolov8 = new Yolov8;
            g_yolov8->load(mgr, modeltype, target_size, use_gpu);
        }
    }

    return JNI_TRUE;
}

// public native boolean openCamera(int facing);
JNIEXPORT jboolean JNICALL Java_ncnn_v5lite_demo_Ncnnv5lite_openCamera(JNIEnv* env, jobject thiz, jint facing)
{
    if (facing < 0 || facing > 1)
        return JNI_FALSE;

    __android_log_print(ANDROID_LOG_DEBUG, "ncnn", "openCamera %d", facing);

    g_camera->open((int)facing);

    return JNI_TRUE;
}

// public native boolean closeCamera();
JNIEXPORT jboolean JNICALL Java_ncnn_v5lite_demo_Ncnnv5lite_closeCamera(JNIEnv* env, jobject thiz)
{
    __android_log_print(ANDROID_LOG_DEBUG, "ncnn", "closeCamera");

    g_camera->close();

    return JNI_TRUE;
}

// public native boolean setOutputWindow(Surface surface);
JNIEXPORT jboolean JNICALL Java_ncnn_v5lite_demo_Ncnnv5lite_setOutputWindow(JNIEnv* env, jobject thiz, jobject surface)
{
    ANativeWindow* win = ANativeWindow_fromSurface(env, surface);

    __android_log_print(ANDROID_LOG_DEBUG, "ncnn", "setOutputWindow %p", win);

    g_camera->set_window(win);

    return JNI_TRUE;
}

// private native void nativeSetListener();
// 没有这一步，report_objects() 里的 g_listener / g_on_detected 永远为 0，
// 回调静默失效（表现为：中文框 / 状态栏 / CSV 记录全部没有任何反应）。
JNIEXPORT void JNICALL Java_ncnn_v5lite_demo_Ncnnv5lite_nativeSetListener(JNIEnv* env, jobject thiz)
{
    if (g_listener)
    {
        env->DeleteGlobalRef(g_listener);
        g_listener = 0;
    }
    g_on_detected = 0;

    jclass cls = env->GetObjectClass(thiz);
    if (!cls) return;

    g_on_detected = env->GetMethodID(cls, "onDetected", "([F[F[I)V");
    if (!g_on_detected)
    {
        env->ExceptionClear();
        __android_log_print(ANDROID_LOG_ERROR, "ncnn", "onDetected method not found");
        return;
    }

    jobject gref = env->NewGlobalRef(thiz);
    if (gref)
    {
        g_listener = gref;
        __android_log_print(ANDROID_LOG_DEBUG, "ncnn", "detect listener registered");
    }
}

}
