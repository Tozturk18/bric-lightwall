#include "led_display.hpp"

#include "led-matrix.h"

#include <stdexcept>
#include <string>
#include <vector>

namespace bric {

LEDDisplay::LEDDisplay(const BricConfig& config) {
  rgb_matrix::RGBMatrix::Options matrix_options;
  matrix_options.hardware_mapping = config.hardware_mapping.c_str();
  matrix_options.rows = config.panel_rows;
  matrix_options.cols = config.panel_cols;
  matrix_options.chain_length = config.panel_chain;
  matrix_options.parallel = config.panel_parallel;
  matrix_options.brightness = config.brightness;

  rgb_matrix::RuntimeOptions runtime_options;
  runtime_options.gpio_slowdown = config.slowdown_gpio;
  runtime_options.daemon = 0;
  runtime_options.drop_privileges = 0;

  matrix_.reset(
      rgb_matrix::RGBMatrix::CreateFromOptions(matrix_options, runtime_options));
  if (!matrix_) {
    throw std::runtime_error("failed to initialize RGBMatrix");
  }

  width_ = config.wall_width;
  height_ = config.wall_height;
  canvas_width_ = matrix_->width();
  canvas_height_ = matrix_->height();
  panel_cols_ = config.panel_cols;
  panel_rows_ = config.panel_rows;
  output_rotation_ = config.output_rotation == 180 ? 180 : 0;
  pixel_mapping_ = parsePixelMapping(config.pixel_mapping);
  validateMapping(config);

  offscreen_ = matrix_->CreateFrameCanvas();
  if (offscreen_ == nullptr) {
    throw std::runtime_error("failed to create RGBMatrix frame canvas");
  }
}

LEDDisplay::~LEDDisplay() {
  try {
    clear();
  } catch (...) {
  }
}

void LEDDisplay::showFrame(const std::uint8_t* rgb, int width, int height) {
  if (rgb == nullptr || width != width_ || height != height_) {
    return;
  }

  const std::uint8_t* pixel = rgb;
  for (int y = 0; y < height_; ++y) {
    for (int x = 0; x < width_; ++x) {
      const MappedPixel mapped = mapPixel(x, y);
      offscreen_->SetPixel(mapped.x, mapped.y, pixel[0], pixel[1], pixel[2]);
      pixel += 3;
    }
  }
  offscreen_ = matrix_->SwapOnVSync(offscreen_);
}

void LEDDisplay::showSolidColor(std::uint8_t red, std::uint8_t green,
                                std::uint8_t blue) {
  offscreen_->Fill(red, green, blue);
  offscreen_ = matrix_->SwapOnVSync(offscreen_);
}

void LEDDisplay::showTestPattern() {
  for (int y = 0; y < height_; ++y) {
    for (int x = 0; x < width_; ++x) {
      const std::uint8_t red =
          static_cast<std::uint8_t>((x * 255) / (width_ > 1 ? width_ - 1 : 1));
      const std::uint8_t green =
          static_cast<std::uint8_t>((y * 255) / (height_ > 1 ? height_ - 1 : 1));
      const std::uint8_t blue = static_cast<std::uint8_t>(((x + y) * 255) /
                                                         (width_ + height_));
      const MappedPixel mapped = mapPixel(x, y);
      offscreen_->SetPixel(mapped.x, mapped.y, red, green, blue);
    }
  }
  offscreen_ = matrix_->SwapOnVSync(offscreen_);
}

void LEDDisplay::clear() {
  if (matrix_ == nullptr || offscreen_ == nullptr) {
    return;
  }
  offscreen_->Fill(0, 0, 0);
  offscreen_ = matrix_->SwapOnVSync(offscreen_);
}

LEDDisplay::MappedPixel LEDDisplay::mapPixel(int x, int y) const {
  const MappedPixel logical = rotateLogicalPixel(x, y);
  x = logical.x;
  y = logical.y;

  if (pixel_mapping_ == PixelMapping::kDirect) {
    return {x, y};
  }

  if (y < panel_rows_) {
    // Logical top half is physical panel 2. Since that panel is mounted
    // rotated 180 degrees, invert both local axes before writing to chain #2.
    return {panel_cols_ + (panel_cols_ - 1 - x), panel_rows_ - 1 - y};
  }

  // Logical bottom half is physical panel 1 in normal orientation.
  return {x, y - panel_rows_};
}

LEDDisplay::MappedPixel LEDDisplay::rotateLogicalPixel(int x, int y) const {
  if (output_rotation_ == 180) {
    return {width_ - 1 - x, height_ - 1 - y};
  }
  return {x, y};
}

LEDDisplay::PixelMapping LEDDisplay::parsePixelMapping(
    const std::string& value) {
  if (value == "direct") {
    return PixelMapping::kDirect;
  }
  if (value == "stacked-panel2-top-rot180" ||
      value == "stacked_panel2_top_rot180" ||
      value == "panel2-top-rot180") {
    return PixelMapping::kStackedPanel2TopRot180;
  }
  throw std::runtime_error("unknown BRIC_PIXEL_MAPPING: " + value);
}

void LEDDisplay::validateMapping(const BricConfig& config) const {
  if (pixel_mapping_ == PixelMapping::kDirect) {
    if (width_ != canvas_width_ || height_ != canvas_height_) {
      throw std::runtime_error("direct mapping needs logical display " +
                               std::to_string(canvas_width_) + "x" +
                               std::to_string(canvas_height_) +
                               " but config expects " +
                               std::to_string(width_) + "x" +
                               std::to_string(height_));
    }
    return;
  }

  if (pixel_mapping_ == PixelMapping::kStackedPanel2TopRot180) {
    if (config.panel_chain != 2 || config.panel_parallel != 1 ||
        width_ != panel_cols_ || height_ != panel_rows_ * 2 ||
        canvas_width_ < panel_cols_ * 2 || canvas_height_ < panel_rows_) {
      throw std::runtime_error(
          "stacked-panel2-top-rot180 mapping needs chain=2 parallel=1 "
          "logical display panel_cols x (panel_rows * 2); matrix canvas is " +
          std::to_string(canvas_width_) + "x" +
          std::to_string(canvas_height_) + " and logical config is " +
          std::to_string(width_) + "x" + std::to_string(height_));
    }
  }
}

}  // namespace bric
