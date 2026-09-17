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
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.view.PixelCopy;
import android.os.Build;
import android.os.Bundle;
import android.util.Base64;
import android.util.Log;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.SubMenu;
import android.view.View;
import android.view.WindowManager;
import android.widget.AdapterView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.PopupMenu;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import android.support.v4.app.ActivityCompat;
import android.support.v4.content.ContextCompat;

import android.os.AsyncTask;
import android.text.method.ScrollingMovementMethod;
import android.widget.LinearLayout;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
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

    /* ---------------- VLM 分析：检测 → 抽框 → 调大模型 → 自然语言结论 ---------------- */
    private float[] lastRects = new float[0];
    private float[] lastProbs = new float[0];
    private int[]   lastLabels = new int[0];
    private TextView vlmResultText;
    private boolean vlmBusy = false;

    private static final String DEFAULT_PROMPT =
            "你是一名工业现场助手。下面是一张实时画面中被检测框选出的目标（已裁剪为若干张小图）。"
            + "请用简洁的中文说明画面里有哪些目标、各自状态是否正常，并指出有无异常或风险。";

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

        // VLM 分析：检测 → 抽框 → 调大模型 → 自然语言结论
        vlmResultText = (TextView) findViewById(R.id.vlmResultText);
        vlmResultText.setMovementMethod(new ScrollingMovementMethod());
        Button buttonVlm = (Button) findViewById(R.id.buttonVlm);
        buttonVlm.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) { runVlm(); }
        });
        Button buttonVlmSettings = (Button) findViewById(R.id.buttonVlmSettings);
        buttonVlmSettings.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) { showVlmSettings(); }
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

    /* ---------------- 菜单：记录历史 / 帮助 / 关于 / 知识文档 ---------------- */

    private void showMainMenu(View anchor)
    {
        PopupMenu menu = new PopupMenu(this, anchor);
        menu.getMenu().add(0, 1, 0, "记录历史");
        menu.getMenu().add(0, 2, 1, "帮助");
        menu.getMenu().add(0, 3, 2, "关于");

        // 知识文档：四系列对比 / 工业场景 / 大模型 / 软件升级 / 扩展研究（内容随研究与软件更新同步）
        SubMenu doc = menu.getMenu().addSubMenu(0, 0, 3, "知识文档");
        doc.add(0, 11, 0, "① 四系列对比");
        doc.add(0, 12, 1, "② 工业场景应用");
        doc.add(0, 13, 2, "③ 结合大模型改进");
        doc.add(0, 14, 3, "④ 软件升级（网盘/GitHub）");
        doc.add(0, 15, 4, "⑤ 扩展更多类别/分割");

        menu.setOnMenuItemClickListener(new PopupMenu.OnMenuItemClickListener() {
            @Override
            public boolean onMenuItemClick(android.view.MenuItem item)
            {
                switch (item.getItemId())
                {
                    case 1: showHistory(); return true;
                    case 2: showHelp();    return true;
                    case 3: showAbout();   return true;
                    case 11: openDoc("compare"); return true;
                    case 12: openDoc("industry"); return true;
                    case 13: openDoc("llm"); return true;
                    case 14: openDoc("upgrade"); return true;
                    case 15: openDoc("expand"); return true;
                }
                return false;
            }
        });
        menu.show();
    }

    private void openDoc(String topic)
    {
        Intent i = new Intent(this, DocActivity.class);
        i.putExtra("topic", topic);
        startActivity(i);
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

    /* ---------------- VLM 分析流水线 ---------------- */

    private void runVlm()
    {
        if (vlmBusy)
        {
            Toast.makeText(this, "分析进行中…", Toast.LENGTH_SHORT).show();
            return;
        }
        if (lastLabels == null || lastLabels.length == 0)
        {
            vlmResultText.setText(R.string.vlm_no_detection);
            return;
        }
        VlmConfig cfg = VlmConfig.load(this);
        if (cfg.endpoint == null || cfg.endpoint.isEmpty())
        {
            vlmResultText.setText(R.string.vlm_empty_config);
            return;
        }
        int w = cameraView.getWidth();
        int h = cameraView.getHeight();
        if (w <= 0 || h <= 0)
        {
            vlmResultText.setText("预览尚未就绪，稍后再试");
            return;
        }
        final Bitmap frame = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
        vlmBusy = true;
        vlmResultText.setText(R.string.vlm_analyzing);
        // PixelCopy 抓取当前相机帧（无需改动 native），裁剪检测框后送大模型
        PixelCopy.request(cameraView, frame, new PixelCopy.OnPixelCopyFinishedListener()
        {
            @Override
            public void onPixelCopyFinished(int result)
            {
                if (result != PixelCopy.SUCCESS)
                {
                    vlmBusy = false;
                    vlmResultText.setText("取帧失败（" + result + "）");
                    return;
                }
                doVlmInBackground(frame, cfg);
            }
        }, null);
    }

    private void doVlmInBackground(final Bitmap frame, final VlmConfig cfg)
    {
        int n = lastLabels.length;
        if (n * 4 > lastRects.length) n = lastRects.length / 4;
        if (n <= 0)
        {
            vlmBusy = false;
            vlmResultText.setText(R.string.vlm_no_detection);
            return;
        }
        final int k = Math.min(n, 5); // 取置信度最高的若干框
        Integer[] idx = new Integer[n];
        for (int i = 0; i < n; i++) idx[i] = i;
        Arrays.sort(idx, new Comparator<Integer>()
        {
            @Override
            public int compare(Integer a, Integer b)
            {
                return Float.compare(lastProbs[b], lastProbs[a]);
            }
        });
        final int fw = frame.getWidth(), fh = frame.getHeight();
        StringBuilder images = new StringBuilder();
        StringBuilder names = new StringBuilder();
        for (int t = 0; t < k; t++)
        {
            int i = idx[t];
            int x0 = Math.max(0, Math.min(fw - 1, (int) (lastRects[i * 4 + 0] * fw)));
            int y0 = Math.max(0, Math.min(fh - 1, (int) (lastRects[i * 4 + 1] * fh)));
            int x1 = Math.max(x0 + 1, Math.min(fw, (int) (lastRects[i * 4 + 2] * fw)));
            int y1 = Math.max(y0 + 1, Math.min(fh, (int) (lastRects[i * 4 + 3] * fh)));
            Bitmap crop = Bitmap.createBitmap(frame, x0, y0, x1 - x0, y1 - y0);
            images.append(bitmapToBase64(crop)).append("\n");
            names.append(CocoLabels.cn(lastLabels[i])).append(" ");
        }
        final String imagesB64 = images.toString();
        final String nameList = names.toString().trim();
        final String prompt = cfg.prompt;

        new AsyncTask<Void, Void, String>()
        {
            @Override
            protected String doInBackground(Void... v)
            {
                HttpURLConnection c = null;
                try
                {
                    String payload = buildVlmJson(imagesB64, nameList, prompt);
                    byte[] body = payload.getBytes("utf-8");
                    c = (HttpURLConnection) new URL(cfg.endpoint).openConnection();
                    c.setRequestMethod("POST");
                    c.setConnectTimeout(15000);
                    c.setReadTimeout(30000);
                    c.setDoOutput(true);
                    c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    if (cfg.apiKey != null && !cfg.apiKey.isEmpty())
                        c.setRequestProperty("Authorization", "Bearer " + cfg.apiKey);
                    OutputStream os = c.getOutputStream();
                    os.write(body);
                    os.close();
                    int code = c.getResponseCode();
                    InputStream is = (code >= 200 && code < 300) ? c.getInputStream() : c.getErrorStream();
                    BufferedReader r = new BufferedReader(new InputStreamReader(is, "utf-8"));
                    StringBuilder out = new StringBuilder();
                    String line;
                    while ((line = r.readLine()) != null) out.append(line);
                    c.disconnect();
                    if (code >= 200 && code < 300) return "OK:" + extractVlmText(out.toString());
                    return "ERR HTTP " + code + ": " + out.toString();
                }
                catch (Exception e)
                {
                    return "ERR:" + e.getMessage();
                }
                finally
                {
                    if (c != null) c.disconnect();
                }
            }

            @Override
            protected void onPostExecute(String res)
            {
                vlmBusy = false;
                if (res.startsWith("OK:")) vlmResultText.setText(res.substring(3));
                else vlmResultText.setText(res);
            }
        }.execute();
    }

    private String bitmapToBase64(Bitmap bm)
    {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        bm.compress(Bitmap.CompressFormat.JPEG, 80, baos);
        return Base64.encodeToString(baos.toByteArray(), Base64.NO_WRAP);
    }

    /** 组装发送给 VLM 端点的 JSON：裁剪图(base64 数组) + 类别名 + 提示词。 */
    private String buildVlmJson(String imagesB64, String nameList, String prompt)
    {
        StringBuilder b = new StringBuilder();
        b.append("{\"images\":[");
        String[] lines = imagesB64.split("\n");
        boolean first = true;
        for (String ln : lines)
        {
            if (ln.isEmpty()) continue;
            if (!first) b.append(",");
            b.append("\"").append(ln).append("\"");
            first = false;
        }
        b.append("],\"names\":\"").append(nameList.replace("\"", "")).append("\",");
        String p = (prompt == null || prompt.isEmpty()) ? DEFAULT_PROMPT : prompt;
        b.append("\"prompt\":\"").append(p.replace("\\", "\\\\").replace("\"", "\\\"")).append("\"}");
        return b.toString();
    }

    /** 从 VLM 端点返回里提取自然语言文本；兼容常见字段，非 JSON 则回退原文。 */
    private String extractVlmText(String json)
    {
        try
        {
            JSONObject o = new JSONObject(json);
            if (o.has("text")) return o.getString("text");
            if (o.has("result")) return o.getString("result");
            if (o.has("content")) return o.getString("content");
            if (o.has("answer")) return o.getString("answer");
        }
        catch (Exception e)
        {
            // 非 JSON，回退原文
        }
        return json;
    }

    private void showVlmSettings()
    {
        VlmConfig cfg = VlmConfig.load(this);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(40, 20, 40, 20);
        final EditText etEndpoint = new EditText(this);
        etEndpoint.setHint(R.string.vlm_endpoint_hint);
        etEndpoint.setText(cfg.endpoint);
        final EditText etKey = new EditText(this);
        etKey.setHint(R.string.vlm_key_hint);
        etKey.setText(cfg.apiKey);
        final EditText etPrompt = new EditText(this);
        etPrompt.setHint("分析提示词（可选，留空用默认）");
        etPrompt.setText(cfg.prompt);
        layout.addView(etEndpoint);
        layout.addView(etKey);
        layout.addView(etPrompt);
        new AlertDialog.Builder(this)
                .setTitle(R.string.vlm_settings_title)
                .setView(layout)
                .setPositiveButton("保存", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w)
                    {
                        VlmConfig.save(MainActivity.this,
                                etEndpoint.getText().toString().trim(),
                                etKey.getText().toString().trim(),
                                etPrompt.getText().toString().trim());
                        Toast.makeText(MainActivity.this, "已保存 VLM 设置", Toast.LENGTH_SHORT).show();
                    }
                })
                .setNegativeButton("取消", null)
                .show();
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

        // 留存最近一帧检测结果，供 VLM 分析抽框使用
        lastRects  = (rects  == null) ? new float[0] : rects.clone();
        lastProbs  = (probs  == null) ? new float[0] : probs.clone();
        lastLabels = (labels == null) ? new int[0]   : labels.clone();

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
