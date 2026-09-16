把 YOLOv5-Lite 的 ncnn 模型文件放在本目录：
- *.param  （网络结构）
- *.bin    （权重）
来源：仓库 model_zoo（github.com/ppogg/ncnn-android-v5lite/tree/master/app/src/main/assets）
或自行用 YOLOv5-Lite 训练后转 ncnn（pnnx/export）。
注意：原工程 assets 目录缺失，构建 APK 前必须先把模型放进来，否则运行即崩溃。
