project(YOLOv8ss)

cmake_minimum_required(VERSION 3.10.2)

set(OpenCV_DIR E:/AndroidSDK/opencv-mobile-2.4.13.7-android/sdk/native/jni)
find_package(OpenCV REQUIRED core imgproc)

set(ncnn_DIR E:/AndroidSDK/ncnn-20210525-android-vulkan/${ANDROID_ABI}/lib/cmake/ncnn)
find_package(ncnn REQUIRED)

add_library(ncnnv5lite SHARED yolov5ncnn.cpp yolov8.cpp ndkcamera.cpp abi_stubs.cpp)

target_link_libraries(ncnnv5lite ncnn ${OpenCV_LIBS} camera2ndk mediandk)
