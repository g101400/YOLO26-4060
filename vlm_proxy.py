#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YOLO-Lite VLM 代理（本地最小可用原型）
=====================================
app 端「VLM 分析」会把检测框裁剪图(base64 JPEG 数组) + 类别名 + 提示词 POST 到这里，
本服务返回自然语言结论 {"text": "..."}。

默认 MOCK 模式：不需要任何 API Key 即可端到端跑通（用类别名+提示词拼出结论）。
要接真实大模型，设置环境变量后启动，脚本会自动走真实接口：
  - OPENAI_API_KEY       走 OpenAI 兼容视觉接口（gpt-4o-mini 等）
  - QWEN_API_KEY         走通义千问视觉接口
  - VLM_ENDPOINT_URL     自定义 OpenAI 兼容 /v1/chat/completions 地址（可选）
  - VLM_MODEL            模型名（默认 gpt-4o-mini）

用法：
  python3 vlm_proxy.py                 # mock 模式，监听 0.0.0.0:8080
  OPENAI_API_KEY=sk-... python3 vlm_proxy.py
  VLM_ENDPOINT_URL=https://.../v1/chat/completions VLM_MODEL=qwen-vl-max python3 vlm_proxy.py

app 端「VLM 设置」里填： http://<本机局域网IP>:8080/v1/vlm
"""
import base64
import hashlib
import json
import os
import urllib.request

from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = "0.0.0.0"
PORT = 8080


def _img_tag(b64: str) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}


def _call_openai_compatible(images, names, prompt, api_key, endpoint, model):
    """调用 OpenAI 兼容视觉接口（OpenAI / 通义千问 / 自建）。"""
    content = []
    if names:
        content.append({"type": "text", "text": "画面中被检测到的目标类别：" + names})
    for b64 in images:
        content.append(_img_tag(b64))
    content.append({"type": "text", "text": prompt})
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 400,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + api_key)
    with urllib.request.urlopen(req, timeout=60) as resp:
        j = json.loads(resp.read().decode("utf-8"))
    return j["choices"][0]["message"]["content"]


def _mock(images, names, prompt):
    """无 Key 时的兜底结论：基于类别名与图片指纹生成稳定可读的中文描述。"""
    n = len(images)
    if not names:
        return ("（MOCK 模式，未配置真实大模型）当前画面未检出明确目标，"
                "请在「VLM 设置」填入端点或设置 OPENAI_API_KEY 启用真实分析。")
    tags = "、".join(names.split())
    # 用首张图内容哈希伪随机给出「状态」描述，保证同一帧结论稳定
    h = int(hashlib.md5(images[0].encode("utf-8")).hexdigest(), 16)
    states = ["状态正常", "外观完整", "摆放整齐", "运行平稳", "无明显异常"]
    risk = ["暂未发现异常风险", "建议保持关注", "建议复核该目标位置", "可结合业务规则进一步判断"]
    s = states[h % len(states)]
    r = risk[(h >> 4) % len(risk)]
    return (f"（MOCK 模式）共检出 {n} 个目标：{tags}。{s}；{r}。"
            f"\n提示：配置真实大模型后，此处会给出基于图像内容的语义分析。")


def handle(images, names, prompt):
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("QWEN_API_KEY")
    endpoint = os.environ.get("VLM_ENDPOINT_URL")
    model = os.environ.get("VLM_MODEL", "gpt-4o-mini")
    if api_key and endpoint:
        try:
            return _call_openai_compatible(images, names, prompt, api_key, endpoint, model)
        except Exception as e:
            return "真实 VLM 调用失败：" + str(e) + "\n（已回退 MOCK）\n" + _mock(images, names, prompt)
    return _mock(images, names, prompt)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def do_POST(self):
        if self.path.rstrip("/") not in ("/v1/vlm", "/vlm"):
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            req = json.loads(raw.decode("utf-8"))
            images = req.get("images", [])
            names = req.get("names", "")
            prompt = req.get("prompt", "")
            text = handle(images, names, prompt)
            self._send(200, {"text": text})
        except Exception as e:
            self._send(400, {"error": str(e)})

    def log_message(self, fmt, *args):
        print("[vlm_proxy]", fmt % args)


if __name__ == "__main__":
    print(f"YOLO-Lite VLM proxy 启动于 http://{HOST}:{PORT}/v1/vlm  (mock 模式除非设置了 API Key)")
    HTTPServer((HOST, PORT), Handler).serve_forever()
