# YOLO26-4060

YOLO-Lite 系列备份（series: v26）—— 由 WorkBuddy 于 2026-09-16 自动同步到 GitHub。

## 内容
- 多系列检测源码 `win_app/`（detector.py 同时支持 v5-Lite anchor-based 与 v8/v11/v26 anchor-free 解码）
- 本系列 ncnn 模型（见下）
- 导出/对拍证据 `export_env/recon/` + 脚本
- 系列规划文档（多系列演进方案 / 版本规划与发布规范）

## 本系列包含的模型
YOLO26: export_env/yolo26n_ncnn_model

## 运行（Windows）
```bash
cd win_app
pip install -r requirements.txt   # 或复用独立 venv
python detector.py --selftest
```

## 来源
本地工作区 `D:/Users/WorkBuddy/ai-vision`。仓库为私有备份，如需公开或改名请告知。
