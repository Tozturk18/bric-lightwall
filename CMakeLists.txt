cmake_minimum_required(VERSION 3.16)

project(bric_tile_receiver VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

set(RGBMATRIX_ROOT "/opt/rpi-rgb-led-matrix" CACHE PATH
    "Path to hzeller/rpi-rgb-led-matrix")
set(RGBMATRIX_INCLUDE_DIR "${RGBMATRIX_ROOT}/include")
set(RGBMATRIX_LIBRARY "${RGBMATRIX_ROOT}/lib/librgbmatrix.a")

if(NOT EXISTS "${RGBMATRIX_INCLUDE_DIR}/led-matrix.h")
  message(FATAL_ERROR "Missing led-matrix.h under ${RGBMATRIX_INCLUDE_DIR}")
endif()

if(NOT EXISTS "${RGBMATRIX_LIBRARY}")
  message(FATAL_ERROR "Missing librgbmatrix.a at ${RGBMATRIX_LIBRARY}")
endif()

add_executable(bric_tile_receiver
  src/main.cpp
  src/bric_config.cpp
  src/frame_reassembler.cpp
  src/led_display.cpp
  src/udp_receiver.cpp
  src/utils.cpp
)

target_include_directories(bric_tile_receiver PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

target_include_directories(bric_tile_receiver SYSTEM PRIVATE
  "${RGBMATRIX_INCLUDE_DIR}"
)

target_compile_options(bric_tile_receiver PRIVATE
  -Wall
  -Wextra
  -Wpedantic
  $<$<CONFIG:Release>:-O3>
  $<$<CONFIG:Release>:-march=native>
  $<$<CONFIG:Release>:-mtune=native>
)

target_link_libraries(bric_tile_receiver PRIVATE
  "${RGBMATRIX_LIBRARY}"
  pthread
  rt
  m
)
