if(NOT ARMSX3_MOLTENVK_ROOT)
    message(FATAL_ERROR "ARMSX3_MOLTENVK_ROOT must name the verified pinned iOS package")
endif()
set(_mvk_library "${ARMSX3_MOLTENVK_ROOT}/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a")
if(NOT EXISTS "${_mvk_library}" OR NOT EXISTS "${ARMSX3_MOLTENVK_ROOT}/include/vulkan/vulkan.h")
    message(FATAL_ERROR "Verified MoltenVK iOS archive/headers are missing")
endif()
add_library(armsx3_ios_moltenvk STATIC IMPORTED)
set_target_properties(armsx3_ios_moltenvk PROPERTIES
    IMPORTED_LOCATION "${_mvk_library}"
    INTERFACE_INCLUDE_DIRECTORIES "${ARMSX3_MOLTENVK_ROOT}/include")
