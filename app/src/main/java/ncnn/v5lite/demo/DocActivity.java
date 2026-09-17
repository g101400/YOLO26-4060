package ncnn.v5lite.demo;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.Toast;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * 知识文档阅读器：加载 assets/docs/<topic>.html。
 *  - 本地内置（离线可用）为单一内容来源，便于随版本打包。
 *  - 「同步最新」联网从本仓库 docs/ 拉取最新版覆盖，便于随研究深入与软件更新持续同步（无需发版）。
 *  - 页内 http(s) 外链（GitHub / 百度网盘）跳转到系统浏览器；相对链接（如 expand.html）在 WebView 内打开。
 */
public class DocActivity extends Activity
{
    private static final String TAG = "DocActivity";
    private WebView webView;
    private String topic;
    private String remoteBase;

    @Override
    protected void onCreate(Bundle savedInstanceState)
    {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_doc);

        topic = getIntent().getStringExtra("topic");
        if (topic == null || topic.isEmpty()) topic = "compare";
        remoteBase = getString(R.string.doc_sync_base);

        webView = (WebView) findViewById(R.id.docWebView);
        webView.getSettings().setJavaScriptEnabled(false);
        webView.getSettings().setBuiltInZoomControls(true);
        webView.getSettings().setDisplayZoomControls(false);
        webView.setWebViewClient(new WebViewClient()
        {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url)
            {
                if (url.startsWith("file://") || url.startsWith("about:"))
                {
                    return false; // 本地/相对链接在 WebView 内打开
                }
                try
                {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                }
                catch (Exception e)
                {
                    Toast.makeText(DocActivity.this, "无法打开链接", Toast.LENGTH_SHORT).show();
                }
                return true; // 外链跳浏览器，WebView 不再处理
            }
        });

        ((Button) findViewById(R.id.btnDocBack)).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) { finish(); }
        });
        ((Button) findViewById(R.id.btnSync)).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) { syncRemote(); }
        });

        loadLocal();
    }

    private void loadLocal()
    {
        webView.loadUrl("file:///android_asset/docs/" + topic + ".html");
    }

    /** 联网拉取仓库最新 docs/<topic>.html 覆盖本地内置内容（失败则保留本地）。 */
    private void syncRemote()
    {
        final String url = remoteBase + topic + ".html";
        new AsyncTask<Void, Void, String>()
        {
            @Override
            protected String doInBackground(Void... v)
            {
                HttpURLConnection c = null;
                try
                {
                    c = (HttpURLConnection) new URL(url).openConnection();
                    c.setConnectTimeout(8000);
                    c.setReadTimeout(8000);
                    c.setRequestProperty("User-Agent", "yololite-doc");
                    int code = c.getResponseCode();
                    if (code != 200) return "HTTP " + code;
                    InputStream is = c.getInputStream();
                    BufferedReader r = new BufferedReader(new InputStreamReader(is, "utf-8"));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = r.readLine()) != null) sb.append(line).append("\n");
                    return "OK:" + sb.toString();
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
                if (res.startsWith("OK:"))
                {
                    webView.loadDataWithBaseURL("file:///android_asset/docs/", res.substring(3),
                            "text/html", "utf-8", null);
                    Toast.makeText(DocActivity.this, "已同步最新内容", Toast.LENGTH_SHORT).show();
                }
                else
                {
                    Toast.makeText(DocActivity.this, "同步失败：" + res, Toast.LENGTH_LONG).show();
                }
            }
        }.execute();
    }
}
