cmake_minimum_required(VERSION 3.21)

project(BinanceBacktestTabCpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Widgets)

add_executable(binance_backtest_tab
    src/main.cpp
    src/BacktestWindow.cpp
    src/BacktestWindow.h
)

target_link_libraries(binance_backtest_tab PRIVATE Qt6::Widgets)

if (MSVC)
    target_compile_options(binance_backtest_tab PRIVATE /Zc:__cplusplus)
endif()
