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

package ncnn.v5lite.demo;

import android.content.res.AssetManager;
import android.view.Surface;

public class Ncnnv5lite
{
    public native boolean loadModel(AssetManager mgr, int modelid, int cpugpu);
    public native boolean openCamera(int facing);
    public native boolean closeCamera();
    public native boolean setOutputWindow(Surface surface);

    /** 每帧检测结果回调（由 JNI 在相机线程调用）。 */
    public interface DetectListener
    {
        /**
         * @param rects  每目标 4 个归一化坐标 x0,y0,x1,y1（相对预览画面，0~1）
         * @param probs  每目标置信度（0~1）
         * @param labels 每目标类别索引（见 CocoLabels）
         */
        void onDetected(float[] rects, float[] probs, int[] labels);
    }

    private DetectListener listener;

    public void setDetectListener(DetectListener l)
    {
        listener = l;
        // 把本对象交给 native：JNI 侧需要它才能把每帧结果回调到 onDetected（相机线程）。
        nativeSetListener();
    }

    /**
     * native 侧缓存本对象的全局引用并解析 onDetected 方法 ID。
     * 注意：onDetected 的方法名与签名 ([F[F[I)V 被 native 按字符串查找，改名会导致回调静默失效。
     */
    private native void nativeSetListener();

    /**
     * JNI 回调入口：签名 ([F[F[I)V 由 native 侧按名字+签名查找，<b>不要改名/改签名</b>。
     * 运行在相机线程，实现类需自行切回 UI 线程。
     */
    public void onDetected(float[] rects, float[] probs, int[] labels)
    {
        DetectListener l = listener;
        if (l != null)
        {
            l.onDetected(rects, probs, labels);
        }
    }

    static {
        System.loadLibrary("ncnnv5lite");
    }
}
