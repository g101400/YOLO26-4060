package ncnn.v5lite.demo;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * VLM 端点配置：保存在应用私有 SharedPreferences（不进任何仓库、不上云）。
 * 默认留空，需用户在 app 内「VLM 设置」填写（或启动本地 vlm_proxy.py 后填入其地址）。
 */
public class VlmConfig
{
    public String endpoint;   // 如 http://192.168.x.x:8080/v1/vlm
    public String apiKey;     // 可选，Bearer Token
    public String prompt;     // 分析提示词（可选）

    private static final String PREFS = "vlm_prefs";

    public static VlmConfig load(Context c)
    {
        SharedPreferences sp = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        VlmConfig cfg = new VlmConfig();
        cfg.endpoint = sp.getString("endpoint", "");
        cfg.apiKey = sp.getString("apiKey", "");
        cfg.prompt = sp.getString("prompt", "");
        return cfg;
    }

    public static void save(Context c, String endpoint, String apiKey, String prompt)
    {
        SharedPreferences sp = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        sp.edit()
          .putString("endpoint", endpoint)
          .putString("apiKey", apiKey)
          .putString("prompt", prompt)
          .apply();
    }
}
