# YOLOv5-Lite 实时检测 —— Windows 版

版本 1.2.1（与安卓端同版本，见 `win_app/version.py`）

## 运行

1. 解压发布包，双击 `YOLOv5-Lite检测.exe`（单文件，已内置模型，无需安装 Python）。
2. 选择模型 / 置信度 → 点「开始检测」。
3. 底部状态栏显示「检测到几个物体、分别是什么、帧率」。

## 功能

- 摄像头实时检测，检测框与标签为**中文**（OpenCV 无中文字形，改用 PIL 绘制）
- 模型：320/416/512 多档 + 量化版（与安卓端完全同源的 ncnn 模型）
- 置信度阈值：0.60 / 0.45 / 0.35 / 0.25 可调
- 检测结果自动存盘：公共「下载」目录 `\YOLOv5-Lite检测记录\detect_日期.csv`
  字段：时间、物体、置信度；UTF-8 BOM，Excel 打开不乱码；**按天保留历史**
- 菜单：`记录`（打开目录 / 清空今日 / 删除全部历史）、`帮助`、`关于`（版本号 + 系列）

## 模型替换

发布包内 `models/` 与 exe 同级时优先使用外部 `models/`，可直接替换其中的
`.param` / `.bin`（需与 YOLOv5-Lite 结构一致），无需重新打包。

## 从源码打包

```bat
"C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv312
.venv312\Scripts\python.exe -m pip install ncnn opencv-python pillow pyinstaller
.venv312\Scripts\python.exe build_win.py
```

要求：Python 3.12（**必须带 tkinter**；workbuddy 自带的 3.13.12 无 Tk，不能用）。
打包脚本会自动执行 `exe --selftest` 做无摄像头自检，并输出
`releases/YOLOv5-Lite检测V1.2.1_win64.zip`。

## 自检 / 排障

```bat
YOLOv5-Lite检测.exe --selftest                  :: 合成图跑通链路
YOLOv5-Lite检测.exe --selftest D:\test.jpg      :: 用真实图片验证检出
```

- 打不开摄像头：换「摄像头」序号 0/1/2/3；确认没有被其它软件占用。
- 无检出：把置信度调到 0.35 或 0.25，或换 `512-lite-c`。
- 记录目录找不到：菜单「记录 → 打开记录目录」。
