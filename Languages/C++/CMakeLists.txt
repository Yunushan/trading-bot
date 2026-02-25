cmake_minimum_required(VERSION 3.21)

project(BinanceBacktestTabCpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

option(TB_REQUIRE_QT_WEBENGINE "Require Qt WebEngine for embedded TradingView/Binance chart modes." ON)

if (WIN32)
    # Prefer a local Qt kit that includes WebEngine so the C++ chart tab can mirror Python modes.
    file(GLOB _tb_qt6_candidates "C:/Qt/6.*/msvc2022_64/lib/cmake/Qt6")
    list(SORT _tb_qt6_candidates COMPARE NATURAL ORDER DESCENDING)

    set(_tb_selected_qt6_dir "")
    foreach(_tb_candidate IN LISTS _tb_qt6_candidates)
        if (EXISTS "${_tb_candidate}/Qt6Config.cmake"
            AND EXISTS "${_tb_candidate}/../Qt6WebEngineWidgets/Qt6WebEngineWidgetsConfig.cmake")
            set(_tb_selected_qt6_dir "${_tb_candidate}")
            break()
        endif()
    endforeach()

    if (_tb_selected_qt6_dir STREQUAL "")
        foreach(_tb_candidate IN LISTS _tb_qt6_candidates)
            if (EXISTS "${_tb_candidate}/Qt6Config.cmake")
                set(_tb_selected_qt6_dir "${_tb_candidate}")
                break()
            endif()
        endforeach()
    endif()

    if (NOT _tb_selected_qt6_dir STREQUAL "")
        set(Qt6_DIR "${_tb_selected_qt6_dir}" CACHE PATH "Qt6 CMake config path" FORCE)
        message(STATUS "Using Qt6_DIR=${Qt6_DIR}")
    endif()

    # Keep optional Qt modules pinned to the same kit as Qt6_DIR to avoid
    # mixed-kit CMake cache entries (for example Qt 6.10 + stale Qt 6.5 paths).
    set(_tb_qt6_cmake_root "")
    if (DEFINED Qt6_DIR AND NOT Qt6_DIR STREQUAL "")
        get_filename_component(_tb_qt6_cmake_root "${Qt6_DIR}" DIRECTORY)
        if (EXISTS "${_tb_qt6_cmake_root}")
            set(QT_ADDITIONAL_PACKAGES_PREFIX_PATH "${_tb_qt6_cmake_root}" CACHE STRING "Qt package search root" FORCE)
            foreach(_tb_qt_module IN ITEMS Qt6WebEngineWidgets Qt6WebEngineCore Qt6WebChannel Qt6Positioning Qt6WebSockets)
                if (EXISTS "${_tb_qt6_cmake_root}/${_tb_qt_module}/${_tb_qt_module}Config.cmake")
                    set(${_tb_qt_module}_DIR "${_tb_qt6_cmake_root}/${_tb_qt_module}" CACHE PATH "${_tb_qt_module} config path" FORCE)
                endif()
            endforeach()
        endif()
    endif()

    if ((NOT DEFINED Vulkan_INCLUDE_DIR)
        OR Vulkan_INCLUDE_DIR STREQUAL ""
        OR Vulkan_INCLUDE_DIR MATCHES "NOTFOUND")
        set(_tb_vulkan_include_candidates
            "${CMAKE_CURRENT_SOURCE_DIR}/../../.vcpkg/installed/x64-windows/include"
            "${CMAKE_CURRENT_SOURCE_DIR}/../../build/binance_cpp/vcpkg_installed/x64-windows/include"
            "$ENV{VCPKG_ROOT}/installed/x64-windows/include"
            "$ENV{USERPROFILE}/vcpkg/installed/x64-windows/include"
            "C:/vcpkg/installed/x64-windows/include"
        )
        foreach(_tb_vulkan_include IN LISTS _tb_vulkan_include_candidates)
            if (EXISTS "${_tb_vulkan_include}/vulkan/vulkan.h")
                set(Vulkan_INCLUDE_DIR "${_tb_vulkan_include}" CACHE PATH "Vulkan include path for Qt WebEngine" FORCE)
                message(STATUS "Using Vulkan_INCLUDE_DIR=${Vulkan_INCLUDE_DIR}")
                break()
            endif()
        endforeach()
    endif()
endif()

find_package(Qt6 6.5 REQUIRED COMPONENTS Widgets Network)
find_package(Qt6WebEngineWidgets QUIET)
find_package(Qt6WebSockets QUIET)

set(HAS_WEBENGINE 0)
if (TARGET Qt6::WebEngineWidgets)
    set(HAS_WEBENGINE 1)
endif()
set(HAS_QT_WEBSOCKETS 0)
if (TARGET Qt6::WebSockets)
    set(HAS_QT_WEBSOCKETS 1)
endif()

if (TB_REQUIRE_QT_WEBENGINE AND NOT HAS_WEBENGINE)
    message(FATAL_ERROR
        "Qt6 WebEngineWidgets was not found for the selected Qt kit. "
        "Install a Qt kit with WebEngine (for example C:/Qt/6.10.1/msvc2022_64) "
        "or configure with -DTB_REQUIRE_QT_WEBENGINE=OFF.")
endif()

set(ICON_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/crypto_forex_logo.ico")
if (WIN32 AND EXISTS "${ICON_SOURCE}")
    set(ICON_PATH "${ICON_SOURCE}")
    set(APP_ICON_RC "${CMAKE_CURRENT_BINARY_DIR}/app_icon.rc")
    configure_file("${CMAKE_CURRENT_SOURCE_DIR}/src/app_icon.rc.in" "${APP_ICON_RC}" @ONLY)
endif()

add_executable(binance_backtest_tab
    src/main.cpp
    src/BinanceRestClient.cpp
    src/BinanceRestClient.h
    src/BinanceWsClient.cpp
    src/BinanceWsClient.h
    src/BacktestWindow.cpp
    src/BacktestWindow.h
    resources.qrc
    ${APP_ICON_RC}
)

target_link_libraries(binance_backtest_tab PRIVATE Qt6::Widgets Qt6::Network)

if (HAS_WEBENGINE)
    target_link_libraries(binance_backtest_tab PRIVATE Qt6::WebEngineWidgets)
endif()
if (HAS_QT_WEBSOCKETS)
    target_link_libraries(binance_backtest_tab PRIVATE Qt6::WebSockets)
endif()
target_compile_definitions(
    binance_backtest_tab
    PRIVATE
        HAS_QT_WEBENGINE=${HAS_WEBENGINE}
        HAS_QT_WEBSOCKETS=${HAS_QT_WEBSOCKETS}
)

if (WIN32)
    # Hide console window and use the embedded icon for the executable
    set_target_properties(binance_backtest_tab PROPERTIES WIN32_EXECUTABLE TRUE)
endif()

if (MSVC)
    target_compile_options(binance_backtest_tab PRIVATE /Zc:__cplusplus)
endif()
