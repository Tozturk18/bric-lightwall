#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace bric {

struct BricConfig {
  std::string config_path = "/etc/bric-lightwall/tile.env";

  std::string tile_name = "bric-tile";
  std::string tile_mac;

  std::string listen_ip = "0.0.0.0";
  std::uint16_t listen_port = 4210;

  int wall_width = 64;
  int wall_height = 64;

  int panel_rows = 32;
  int panel_cols = 64;
  int panel_chain = 2;
  int panel_parallel = 1;
  int brightness = 40;

  std::string hardware_mapping = "regular";
  std::string pixel_mapping = "stacked-panel2-top-rot180";
  int output_rotation = 180;
  int slowdown_gpio = 4;
  int frame_timeout_ms = 100;
  int socket_rcvbuf = 8388608;
  std::string idle_pattern = "blank";

  std::size_t frameBytes() const;
};

BricConfig loadConfig(const std::string& path);

std::string configSummary(const BricConfig& config);

}  // namespace bric
