// ABI shim: opencv-mobile-2.4.13.7-android (nihui tag v36) was built with a
// newer NDK (>= r23), whose libc++/libomp expose two symbols that NDK 21.3.6528147
// does not provide. ncnn 20210525 links fine; only the opencv static libs need
// these, so we supply them here instead of re-downloading a 1GB+ NDK (which would
// also risk breaking AGP 3.5.4 + CMake 3.10.2 toolchain integration).
//
//   - __libcpp_verbose_abort   : added to libc++ in NDK r23
//   - __kmpc_dispatch_deinit   : added to LLVM libomp in NDK r22/r23
//
// These are referenced by libopencv_core.a; providing them lets the static link
// succeed. opencv uses a static (monotonic) parallel-for schedule, so the OpenMP
// dispatch-cleanup stub is effectively a no-op.

#include <cstdio>
#include <cstdlib>
#include <cstdarg>

// libc++ (NDK >= r23) verbose-abort hook.
namespace std {
namespace __ndk1 {
void __libcpp_verbose_abort(char const* format, ...) {
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
    abort();
}
}  // namespace __ndk1
}  // namespace std

// LLVM OpenMP runtime (NDK >= r22/r23) dispatch cleanup.
extern "C" void __kmpc_dispatch_deinit(void* /*loc*/, int /*tid*/) {
    // no-op for static schedule
}
