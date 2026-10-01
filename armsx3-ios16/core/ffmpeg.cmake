# iOS libraries must be cross-compiled first by build-ffmpeg.sh.
# Never use upstream's macOS prebuilt download on an iPhone target.
if(NOT IS_DIRECTORY "${ARMSX3_FFMPEG_ROOT}/include")
    message(FATAL_ERROR "Set ARMSX3_FFMPEG_ROOT to the iOS FFmpeg installation")
endif()
add_library(3rdparty_ffmpeg INTERFACE)
foreach(component avformat avcodec avutil swscale swresample)
    set(archive "${ARMSX3_FFMPEG_ROOT}/lib/lib${component}.a")
    if(NOT EXISTS "${archive}")
        message(FATAL_ERROR "Missing iOS FFmpeg archive: ${archive}")
    endif()
    add_library(ios_ffmpeg_${component} STATIC IMPORTED GLOBAL)
    set_target_properties(ios_ffmpeg_${component} PROPERTIES
        IMPORTED_LOCATION "${archive}"
        INTERFACE_INCLUDE_DIRECTORIES "${ARMSX3_FFMPEG_ROOT}/include")
    target_link_libraries(3rdparty_ffmpeg INTERFACE ios_ffmpeg_${component})
endforeach()
target_link_libraries(3rdparty_ffmpeg INTERFACE z iconv
    "-framework CoreFoundation" "-framework CoreMedia"
    "-framework CoreVideo" "-framework VideoToolbox"
    "-framework AudioToolbox" "-framework Security")
