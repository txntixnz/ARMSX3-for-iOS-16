# P2 requires all core objects to participate in a real link. Undefined symbols
# remain errors; do not use dynamic_lookup or dead-strip the unreferenced core.
include("${CMAKE_SOURCE_DIR}/ios-core/moltenvk.cmake")
add_library(ARMSX3Core SHARED CoreBridge.cpp FrontendHooks.cpp Intake.cpp
    Runtime.cpp RuntimeFrontend.cpp RuntimeDispatch.mm RuntimeCapture.cpp GameImport.cpp
    GraphicsDevice.cpp GraphicsCheck.cpp
    "${CMAKE_SOURCE_DIR}/ios/src/StartupLog.mm"
    "${CMAKE_SOURCE_DIR}/rpcs3/rpcs3_version.cpp"
    "${CMAKE_SOURCE_DIR}/rpcs3/Input/pad_thread.cpp"
    "${CMAKE_SOURCE_DIR}/rpcs3/Input/product_info.cpp"
    "${CMAKE_SOURCE_DIR}/rpcs3/Input/mouse_gyro_handler.cpp"
    "${CMAKE_SOURCE_DIR}/rpcs3/Input/ps_move_config.cpp"
    "${CMAKE_SOURCE_DIR}/rpcs3/Input/ps_move_tracker.cpp")
target_sources(usb-1.0-static PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/LibusbClock.c")
target_compile_definitions(ARMSX3Core PRIVATE ARMSX3_IOS=1)
target_include_directories(ARMSX3Core PRIVATE
    "${CMAKE_SOURCE_DIR}/ios/src"
    "${CMAKE_SOURCE_DIR}/3rdparty/yaml-cpp/yaml-cpp/include")
target_compile_options(ARMSX3Core PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
target_link_libraries(ARMSX3Core PRIVATE rpcs3_emu 3rdparty::fusion
    armsx3_ios_moltenvk
    "-framework Foundation" "-framework CoreFoundation" "-framework Security"
    "-framework AudioToolbox" "-framework CoreMIDI" "-framework CoreAudio"
    "-framework Metal" "-framework QuartzCore" "-framework CoreGraphics"
    "-framework IOSurface" "-framework UIKit" iconv)
target_link_options(ARMSX3Core PRIVATE
    "LINKER:-force_load,$<TARGET_FILE:rpcs3_emu>"
    "LINKER:-undefined,error")
set_target_properties(ARMSX3Core PROPERTIES
    CXX_STANDARD 23 CXX_STANDARD_REQUIRED YES OBJCXX_STANDARD 23
    OUTPUT_NAME ARMSX3Core INSTALL_NAME_DIR "@rpath"
    BUILD_WITH_INSTALL_NAME_DIR YES)

add_executable(ARMSX3CoreLoadTest MACOSX_BUNDLE
    App.mm "${CMAKE_SOURCE_DIR}/ios/src/StartupLog.mm")
target_include_directories(ARMSX3CoreLoadTest PRIVATE "${CMAKE_SOURCE_DIR}/ios/src")
target_compile_options(ARMSX3CoreLoadTest PRIVATE -fobjc-arc)
target_link_libraries(ARMSX3CoreLoadTest PRIVATE "-framework UIKit" "-framework Foundation" "-framework UniformTypeIdentifiers")
# Deliberately loaded by the button after logging starts, never by dyld at launch.
add_dependencies(ARMSX3CoreLoadTest ARMSX3Core)
set_target_properties(ARMSX3CoreLoadTest PROPERTIES
    CXX_STANDARD 23 OBJCXX_STANDARD 23
    RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_BINARY_DIR}"
    OUTPUT_NAME ARMSX3CoreLoadTest
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in")
add_custom_command(TARGET ARMSX3CoreLoadTest POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_BUNDLE_DIR:ARMSX3CoreLoadTest>/Frameworks"
    COMMAND ${CMAKE_COMMAND} -E copy "$<TARGET_FILE:ARMSX3Core>"
        "$<TARGET_BUNDLE_DIR:ARMSX3CoreLoadTest>/Frameworks/libARMSX3Core.dylib"
    COMMAND ${CMAKE_COMMAND} -E copy_directory "${ARMSX3_MOLTENVK_ROOT}/licenses"
        "$<TARGET_BUNDLE_DIR:ARMSX3CoreLoadTest>/ThirdParty/MoltenVK")
