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

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.widget.AdapterView;
import android.widget.Button;
import android.widget.PopupMenu;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import android.support.v4.app.ActivityCompat;
import android.support.v4.content.ContextCompat;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

public class MainActivity extends Activity implements SurfaceHolder.Callback, Ncnnv5lite.DetectListener
{
    public static final int REQUEST_PERM = 100;

    private Ncnnv5lite ncnnyolov5 = new Ncnnv5lite();
    private int facing = 0;

    private Spinner spinnerModel;
    private Spinner spinnerCPUGPU;
    private int current_model = 0;    // 默认 yolov8n_320（最快，实时友好；1=416，2=640 最准）
    private int current_cpugpu = 0;
    private boolean uiReady = false;  // 避免 Spinner 初始化回弹触发多余 reload

    private SurfaceView cameraView;
    private OverlayView overlayView;
    private TextView statusText;
    private TextView logInfoText;
    private Button buttonToggleLog;

    private DetectLog detectLog;
    private boolean logEnabled = true;
    private int logRows = 0;

    /** 记录节流：仅在「类别组合」发生变化且距上次写入 ≥700ms 时落盘，避免每帧刷爆 CSV。 */
    private String lastSignature = "";
    private long lastLogMs = 0;

    private long lastFrameMs = 0;
    private float fps = 0f;

    private final java.text.SimpleDateFormat timeFmt =
            new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.CHINA);

    /** Called when the activity is first created. */
    @Override
    public void onCreate(Bundle savedInstanceState)
    {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.main);

        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        cameraView = (SurfaceView) findViewById(R.id.cameraview);
        overlayView = (OverlayView) findViewById(R.id.overlay);
        statusText = (TextView) findViewById(R.id.statusText);
        logInfoText = (TextView) findViewById(R.id.logInfoText);
        buttonToggleLog = (Button) findViewById(R.id.buttonToggleLog);

        cameraView.getHolder().setFormat(PixelFormat.RGBA_8888);
        cameraView.getHolder().addCallback(this);

        detectLog = new DetectLog(this);
        logRows = detectLog.rowsToday();
        ncnnyolov5.setDetectListener(this);

        Button buttonSwitchCamera = (Button) findViewById(R.id.buttonSwitchCamera);
        buttonSwitchCamera.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View arg0) {
                int new_facing = 1 - facing;
                ncnnyolov5.closeCamera();
                ncnnyolov5.openCamera(new_facing);
                facing = new_facing;
            }
        });

        Button buttonClearLog = (Button) findViewById(R.id.buttonClearLog);
        buttonClearLog.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                detectLog.clearToday();
                logRows = 0;
                lastSignature = "";
                refreshLogInfo();
                Toast.makeText(MainActivity.this, "今日记录已清空（历史按天保留）", Toast.LENGTH_SHORT).show();
            }
        });

        buttonToggleLog.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                logEnabled = !logEnabled;
                buttonToggleLog.setText(logEnabled ? "记录：开" : "记录：关");
                Toast.makeText(MainActivity.this, logEnabled ? "已开启结果记录" : "已暂停结果记录",
                        Toast.LENGTH_SHORT).show();
            }
        });

        // 右上角菜单：记录历史 / 帮助 / 关于
        View buttonMenu = findViewById(R.id.buttonMenu);
        buttonMenu.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showMainMenu(v);
            }
        });

        spinnerModel = (Spinner) findViewById(R.id.spinnerModel);
        spinnerModel.setSelection(current_model);
        spinnerModel.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> arg0, View arg1, int position, long id)
            {
                if (!uiReady) return;
                if (position != current_model)
                {
                    current_model = position;
                    reload();
                }
            }

            @Override
            public void onNothingSelected(AdapterView<?> arg0)
            {
            }
        });

        spinnerCPUGPU = (Spinner) findViewById(R.id.spinnerCPUGPU);
        spinnerCPUGPU.setSelection(current_cpugpu);
        spinnerCPUGPU.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> arg0, View arg1, int position, long id)
            {
                if (!uiReady) return;
                if (position != current_cpugpu)
                {
                    current_cpugpu = position;
                    reload();
                }
            }

            @Override
            public void onNothingSelected(AdapterView<?> arg0)
            {
            }
        });

        uiReady = true;
        refreshLogInfo();
        reload();
    }

    private void reload()
    {
        boolean ret_init = ncnnyolov5.loadModel(getAssets(), current_model, current_cpugpu);
        if (!ret_init)
        {
            Log.e("MainActivity", "ncnnyolov5 loadModel failed");
        }
    }

    /* ---------------- 菜单：记录历史 / 帮助 / 关于 ---------------- */

    private void showMainMenu(View anchor)
    {
        PopupMenu menu = new PopupMenu(this, anchor);
        menu.getMenu().add(0, 1, 0, "记录历史");
        menu.getMenu().add(0, 2, 1, "帮助");
        menu.getMenu().add(0, 3, 2, "关于");
        menu.setOnMenuItemClickListener(new PopupMenu.OnMenuItemClickListener() {
            @Override
            public boolean onMenuItemClick(android.view.MenuItem item)
            {
                switch (item.getItemId())
                {
                    case 1: showHistory(); return true;
                    case 2: showHelp();    return true;
                    case 3: showAbout();   return true;
                }
                return false;
            }
        });
        menu.show();
    }

    private void showHelp()
    {
        new AlertDialog.Builder(this)
                .setTitle("帮助")
                .setMessage(getString(R.string.help_text))
                .setPositiveButton("知道了", null)
                .show();
    }

    private void showAbout()
    {
        new AlertDialog.Builder(this)
                .setTitle("关于")
                .setMessage(getString(R.string.about_text, appVersion(), seriesName()))
                .setPositiveButton("关闭", null)
                .show();
    }

    private void showHistory()
    {
        List<DetectLog.Item> items = detectLog.history();
        if (items.isEmpty())
        {
            new AlertDialog.Builder(this)
                    .setTitle("记录历史")
                    .setMessage("暂无历史记录。\n记录保存在：" + detectLog.location())
                    .setPositiveButton("关闭", null)
                    .show();
            return;
        }

        final String[] names = new String[items.size()];
        for (int i = 0; i < items.size(); i++)
        {
            DetectLog.Item it = items.get(i);
            names[i] = it.prettyDate() + "    " + it.rows + " 条";
        }

        AlertDialog.Builder b = new AlertDialog.Builder(this)
                .setTitle("记录历史（共 " + items.size() + " 天）")
                .setItems(names, null)
                .setNegativeButton("关闭", null)
                .setPositiveButton("删除全部", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int which)
                    {
                        int n = detectLog.clearAll();
                        logRows = 0;
                        lastSignature = "";
                        refreshLogInfo();
                        Toast.makeText(MainActivity.this, "已删除 " + n + " 个历史文件", Toast.LENGTH_SHORT).show();
                    }
                });
        b.show();
    }

    /* ---------------- 版本信息（版本号来自 manifest，单一事实来源） ---------------- */

    private String appVersion()
    {
        try
        {
            PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
            return pi.versionName;
        }
        catch (PackageManager.NameNotFoundException e)
        {
            return "未知";
        }
    }

    /**
     * 版本规划（2026-09-16 定）：
     *   1.x = YOLOv5-Lite 系列，2.x = YOLOv8 系列，3.x = YOLO11 系列，6.x = YOLO26 系列
     * 4.x / 5.x 预留未启用。详见 版本规划与发布规范.md / 多系列演进方案_v5-v8-v11-v26.md
     */
    private String seriesName()
    {
        String v = appVersion();
        if (v.startsWith("1.")) return "YOLOv5-Lite 系列";
        if (v.startsWith("2.")) return "YOLOv8 系列";
        if (v.startsWith("3.")) return "YOLO11 系列";
        if (v.startsWith("6.")) return "YOLO26 系列";
        return "未知系列";
    }

    /* ---------------- 检测结果回调（相机线程 → UI 线程） ---------------- */

    @Override
    public void onDetected(final float[] rects, final float[] probs, final int[] labels)
    {
        long now = System.currentTimeMillis();
        if (lastFrameMs > 0)
        {
            long dt = now - lastFrameMs;
            if (dt > 0)
            {
                float inst = 1000f / dt;
                fps = (fps == 0f) ? inst : (fps * 0.85f + inst * 0.15f);
            }
        }
        lastFrameMs = now;

        final long nowMs = now;
        final float fpsNow = fps;
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                overlayView.setResults(rects, probs, labels);
                updateStatus(labels, fpsNow);
                maybeLog(labels, probs, nowMs);
            }
        });
    }

    /** 状态栏：检测到几个物体，分别是什么。 */
    private void updateStatus(int[] labels, float fpsNow)
    {
        if (labels == null || labels.length == 0)
        {
            statusText.setText("未检测到物体    " + String.format(Locale.CHINA, "%.0f FPS", fpsNow));
            return;
        }

        Map<String, Integer> counts = new LinkedHashMap<String, Integer>();
        for (int lb : labels)
        {
            String name = CocoLabels.cn(lb);
            Integer c = counts.get(name);
            counts.put(name, (c == null) ? 1 : (c + 1));
        }

        StringBuilder sb = new StringBuilder();
        sb.append("检测到 ").append(labels.length).append(" 个：");
        boolean first = true;
        for (Map.Entry<String, Integer> e : counts.entrySet())
        {
            if (!first) sb.append("、");
            sb.append(e.getKey()).append("×").append(e.getValue());
            first = false;
        }
        sb.append("    ").append(String.format(Locale.CHINA, "%.0f FPS", fpsNow));
        statusText.setText(sb.toString());
    }

    /** 自动记录：时间 / 物体 / 置信度，逐目标一行，按天分文件保留历史。 */
    private void maybeLog(int[] labels, float[] probs, long nowMs)
    {
        if (!logEnabled || labels == null || labels.length == 0) return;

        Map<String, Integer> counts = new TreeMap<String, Integer>();
        for (int lb : labels)
        {
            String name = CocoLabels.cn(lb);
            Integer c = counts.get(name);
            counts.put(name, (c == null) ? 1 : (c + 1));
        }
        StringBuilder sig = new StringBuilder();
        for (Map.Entry<String, Integer> e : counts.entrySet())
        {
            sig.append(e.getKey()).append(':').append(e.getValue()).append(';');
        }
        String signature = sig.toString();

        if (signature.equals(lastSignature)) return;      // 画面内容未变，不重复写入
        if (nowMs - lastLogMs < 700) return;              // 变化过于频繁，节流

        lastSignature = signature;
        lastLogMs = nowMs;

        String time = timeFmt.format(new java.util.Date(nowMs));
        for (int i = 0; i < labels.length; i++)
        {
            if (detectLog.append(time, CocoLabels.cn(labels[i]), probs[i]))
            {
                logRows++;
            }
        }
        refreshLogInfo();
    }

    private void refreshLogInfo()
    {
        logInfoText.setText("记录：" + logRows + " 条    " + detectLog.location());
    }

    /* ---------------- 生命周期 / Surface / 权限 ---------------- */

    @Override
    public void surfaceChanged(SurfaceHolder holder, int format, int width, int height)
    {
        ncnnyolov5.setOutputWindow(holder.getSurface());
    }

    @Override
    public void surfaceCreated(SurfaceHolder holder)
    {
    }

    @Override
    public void surfaceDestroyed(SurfaceHolder holder)
    {
    }

    @Override
    public void onResume()
    {
        super.onResume();
        ensurePermissions();
    }

    /** 相机权限必选；Android 9 及以下写公共下载目录还需存储权限（Android 10+ 走 MediaStore，免权限）。 */
    private void ensurePermissions()
    {
        List<String> need = new ArrayList<String>();
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                != PackageManager.PERMISSION_GRANTED)
        {
            need.add(Manifest.permission.CAMERA);
        }
        if (Build.VERSION.SDK_INT <= 28
                && ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != PackageManager.PERMISSION_GRANTED)
        {
            need.add(Manifest.permission.WRITE_EXTERNAL_STORAGE);
        }

        if (!need.isEmpty())
        {
            ActivityCompat.requestPermissions(this, need.toArray(new String[need.size()]), REQUEST_PERM);
        }
        else
        {
            ncnnyolov5.openCamera(facing);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults)
    {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQUEST_PERM) return;

        boolean cameraOk = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED;
        boolean storageOk = Build.VERSION.SDK_INT > 28
                || ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE)
                == PackageManager.PERMISSION_GRANTED;

        if (cameraOk)
        {
            ncnnyolov5.openCamera(facing);
        }
        else
        {
            Toast.makeText(this, "需要相机权限才能检测", Toast.LENGTH_LONG).show();
        }

        if (storageOk)
        {
            // 权限到位后重建记录器，确保当天文件建立在公共下载目录
            detectLog = new DetectLog(this);
            logRows = detectLog.rowsToday();
            refreshLogInfo();
        }
        else
        {
            Toast.makeText(this, "未授予存储权限，记录将不可用", Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    public void onPause()
    {
        super.onPause();

        ncnnyolov5.closeCamera();
    }
}
