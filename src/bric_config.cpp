#include "bric_config.hpp"

#include "utils.hpp"

#include <fstream>
#include <sstream>
#include <string>

namespace bric {
namespace {

void applyConfigValue(BricConfig& config, const std::string& key,
                      const std::string& value) {
  int int_value = 0;

  if (key == "BRIC_TILE_NAME") {
    config.tile_name = value;
  } else if (key == "BRIC_TILE_MAC") {
    config.tile_mac = value;
  } else if (key == "BRIC_LISTEN_IP") {
    config.listen_ip = value;
  } else if (key == "BRIC_LISTEN_PORT" && parseInt(value, &int_value)) {
    config.listen_port =
        static_cast<std::uint16_t>(clampInt(int_value, 1, 65535));
  } else if (key == "BRIC_WALL_WIDTH" && parseInt(value, &int_value)) {
    config.wall_width = clampInt(int_value, 1, 8192);
  } else if (key == "BRIC_WALL_HEIGHT" && parseInt(value, &int_value)) {
    config.wall_height = clampInt(int_value, 1, 8192);
  } else if (key == "BRIC_PANEL_ROWS" && parseInt(value, &int_value)) {
    config.panel_rows = clampInt(int_value, 1, 128);
  } else if (key == "BRIC_PANEL_COLS" && parseInt(value, &int_value)) {
    config.panel_cols = clampInt(int_value, 1, 256);
  } else if (key == "BRIC_PANEL_CHAIN" && parseInt(value, &int_value)) {
    config.panel_chain = clampInt(int_value, 1, 64);
  } else if (key == "BRIC_PANEL_PARALLEL" && parseInt(value, &int_value)) {
    config.panel_parallel = clampInt(int_value, 1, 8);
  } else if (key == "BRIC_BRIGHTNESS" && parseInt(value, &int_value)) {
    config.brightness = clampInt(int_value, 1, 100);
  } else if (key == "BRIC_HARDWARE_MAPPING") {
    config.hardware_mapping = value;
  } else if (key == "BRIC_PIXEL_MAPPING") {
    config.pixel_mapping = value;
  } else if (key == "BRIC_OUTPUT_ROTATION" && parseInt(value, &int_value)) {
    config.output_rotation = int_value == 180 ? 180 : 0;
  } else if (key == "BRIC_SLOWDOWN_GPIO" && parseInt(value, &int_value)) {
    config.slowdown_gpio = clampInt(int_value, 0, 10);
  } else if (key == "BRIC_FRAME_TIMEOUT_MS" && parseInt(value, &int_value)) {
    config.frame_timeout_ms = clampInt(int_value, 1, 5000);
  } else if (key == "BRIC_SOCKET_RCVBUF" && parseInt(value, &int_value)) {
    config.socket_rcvbuf = clampInt(int_value, 65536, 64 * 1024 * 1024);
  } else if (key == "BRIC_IDLE_PATTERN") {
    config.idle_pattern = value;
  }
}

std::string stripOptionalQuotes(const std::string& value) {
  if (value.size() >= 2) {
    const char first = value.front();
    const char last = value.back();
    if ((first == '"' && last == '"') || (first == '\'' && last == '\'')) {
      return value.substr(1, value.size() - 2);
    }
  }
  return value;
}

}  // namespace

std::size_t BricConfig::frameBytes() const {
  return static_cast<std::size_t>(wall_width) *
         static_cast<std::size_t>(wall_height) * 3U;
}

BricConfig loadConfig(const std::string& path) {
  BricConfig config;
  config.config_path = path;

  std::ifstream input(path);
  std::string line;
  while (std::getline(input, line)) {
    line = trim(line);
    if (line.empty() || line[0] == '#') {
      continue;
    }

    const std::size_t equals = line.find('=');
    if (equals == std::string::npos) {
      continue;
    }

    const std::string key = trim(line.substr(0, equals));
    const std::string value =
        stripOptionalQuotes(trim(line.substr(equals + 1)));
    if (!key.empty()) {
      applyConfigValue(config, key, value);
    }
  }

  if (config.tile_mac.empty() || config.tile_mac == "auto") {
    config.tile_mac = getInterfaceMac("eth0");
  }

  return config;
}

std::string configSummary(const BricConfig& config) {
  std::ostringstream out;
  out << "tile=" << config.tile_name << " mac=" << config.tile_mac
      << " listen=" << config.listen_ip << ":" << config.listen_port
      << " display=" << config.wall_width << "x" << config.wall_height
      << " panel_rows=" << config.panel_rows
      << " panel_cols=" << config.panel_cols
      << " chain=" << config.panel_chain
      << " parallel=" << config.panel_parallel
      << " brightness=" << config.brightness
      << " hardware_mapping=" << config.hardware_mapping
      << " pixel_mapping=" << config.pixel_mapping
      << " output_rotation=" << config.output_rotation
      << " slowdown_gpio=" << config.slowdown_gpio
      << " frame_timeout_ms=" << config.frame_timeout_ms
      << " socket_rcvbuf=" << config.socket_rcvbuf;
  return out.str();
}

}  // namespace bric
