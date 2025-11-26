cmake_minimum_required(VERSION 3.21)

project(BinanceBacktestTabCpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Widgets WebEngineWidgets)

set(HAS_WEBENGINE 0)
if (TARGET Qt6::WebEngineWidgets)
    set(HAS_WEBENGINE 1)
endif()

set(ICON_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../Languages/Python/Crypto-Exchanges/Binance/app/assets/binance_icon.ico")
if (WIN32 AND EXISTS "${ICON_SOURCE}")
    set(ICON_PATH "${ICON_SOURCE}")
    set(APP_ICON_RC "${CMAKE_CURRENT_BINARY_DIR}/app_icon.rc")
    configure_file("${CMAKE_CURRENT_SOURCE_DIR}/src/app_icon.rc.in" "${APP_ICON_RC}" @ONLY)
endif()

add_executable(binance_backtest_tab
    src/main.cpp
    src/BacktestWindow.cpp
    src/BacktestWindow.h
    resources.qrc
    ${APP_ICON_RC}
)

target_link_libraries(binance_backtest_tab PRIVATE Qt6::Widgets)

if (HAS_WEBENGINE)
    target_link_libraries(binance_backtest_tab PRIVATE Qt6::WebEngineWidgets)
endif()
target_compile_definitions(binance_backtest_tab PRIVATE HAS_QT_WEBENGINE=${HAS_WEBENGINE})

if (WIN32)
    # Hide console window and use the embedded icon for the executable
    set_target_properties(binance_backtest_tab PROPERTIES WIN32_EXECUTABLE TRUE)
endif()

if (MSVC)
    target_compile_options(binance_backtest_tab PRIVATE /Zc:__cplusplus)
endif()
