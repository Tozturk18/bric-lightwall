#pragma once

#include "bric_config.hpp"

#include <cstdint>
#include <memory>

namespace rgb_matrix {
class RGBMatrix;
class FrameCanvas;
}  // namespace rgb_matrix

namespace bric {

class LEDDisplay {
 public:
  explicit LEDDisplay(const BricConfig& config);
  ~LEDDisplay();

  LEDDisplay(const LEDDisplay&) = delete;
  LEDDisplay& operator=(const LEDDisplay&) = delete;

  void showFrame(const std::uint8_t* rgb, int width, int height);
  void showSolidColor(std::uint8_t red, std::uint8_t green, std::uint8_t blue);
  void showTestPattern();
  void clear();

  int width() const { return width_; }
  int height() const { return height_; }

 private:
  enum class PixelMapping {
    kDirect,
    kStackedPanel2TopRot180,
  };

  struct MappedPixel {
    int x;
    int y;
  };

  static PixelMapping parsePixelMapping(const std::string& value);
  void validateMapping(const BricConfig& config) const;
  MappedPixel mapPixel(int x, int y) const;
  MappedPixel rotateLogicalPixel(int x, int y) const;

  std::unique_ptr<rgb_matrix::RGBMatrix> matrix_;
  rgb_matrix::FrameCanvas* offscreen_ = nullptr;
  int width_ = 0;
  int height_ = 0;
  int canvas_width_ = 0;
  int canvas_height_ = 0;
  int panel_cols_ = 0;
  int panel_rows_ = 0;
  int output_rotation_ = 0;
  PixelMapping pixel_mapping_ = PixelMapping::kDirect;
};

}  // namespace bric
