# SPDX-License-Identifier: GPL-2.0-only
# Standalone P0 target: cmake -S ios -B build-ios -G Xcode -DCMAKE_SYSTEM_NAME=iOS ...
cmake_minimum_required(VERSION 3.28)
project(ARMSX3IOSProbe LANGUAGES C CXX OBJC OBJCXX)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
    message(FATAL_ERROR "This target requires an iPhoneOS SDK, not a macOS or Linux SDK")
endif()
if(NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64")
    message(FATAL_ERROR "P0 targets arm64 devices; simulator is not a JIT validation target")
endif()
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_OBJCXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OBJCXX_STANDARD_REQUIRED ON)
get_filename_component(ARMSX3_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/UPSTREAM_COMMIT" ARMSX3_SOURCE_COMMIT)
string(STRIP "${ARMSX3_SOURCE_COMMIT}" ARMSX3_SOURCE_COMMIT)
add_executable(ARMSX3IOSProbe MACOSX_BUNDLE
    src/App.mm src/Diagnostics.mm
    "${ARMSX3_ROOT}/rpcs3/Emu/RSX/VK/vkutils/metal_layer.mm"
    "${ARMSX3_ROOT}/darwin/util/sysinfo_darwin.mm")
target_include_directories(ARMSX3IOSProbe PRIVATE "${ARMSX3_ROOT}/rpcs3")
target_compile_options(ARMSX3IOSProbe PRIVATE -fobjc-arc -mcpu=apple-a15 -Wall -Wextra)
target_compile_definitions(ARMSX3IOSProbe PRIVATE ARMSX3_SOURCE_COMMIT="${ARMSX3_SOURCE_COMMIT}")
target_link_libraries(ARMSX3IOSProbe PRIVATE
    "-framework UIKit" "-framework Foundation" "-framework Metal" "-framework QuartzCore"
    "-framework CoreGraphics")
set_target_properties(ARMSX3IOSProbe PROPERTIES
    OUTPUT_NAME ARMSX3iOSProbe
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in"
    XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "org.armsx3.experimental.ios16probe"
    XCODE_ATTRIBUTE_IPHONEOS_DEPLOYMENT_TARGET "16.0"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1"
    XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO"
    XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED "NO"
    XCODE_ATTRIBUTE_ENABLE_BITCODE "NO"
    XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC "YES")
message(STATUS "Building P0 platform probe; emulator core and game boot are NOT included")
