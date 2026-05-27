#pragma once

#include "bric_protocol.hpp"

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace bric {

struct ReassemblerResult {
  bool completed = false;
  bool bad_packet = false;
  bool bad_size_frame = false;
  bool dropped_incomplete = false;
  bool ignored_stale = false;
  std::uint32_t frame_id = 0;
  const std::uint8_t* frame_data = nullptr;
  std::size_t frame_size = 0;
};

class FrameReassembler {
 public:
  FrameReassembler(int display_width, int display_height, int timeout_ms);

  ReassemblerResult processPacket(const PacketHeader& header,
                                  const std::uint8_t* payload,
                                  std::chrono::steady_clock::time_point now);

  bool expireStale(std::chrono::steady_clock::time_point now);

  int displayWidth() const { return display_width_; }
  int displayHeight() const { return display_height_; }
  std::size_t frameBytes() const { return frame_bytes_; }

 private:
  bool startFrame(const PacketHeader& header,
                  std::chrono::steady_clock::time_point now);
  bool inferOrValidateChunkPayloadSize(const PacketHeader& header,
                                       std::size_t* expected_payload_size);
  void dropActiveFrame();
  bool isNewerFrame(std::uint32_t candidate, std::uint32_t reference) const;
  bool markBadSizeFrame(std::uint32_t frame_id);

  int display_width_;
  int display_height_;
  std::size_t frame_bytes_;
  std::chrono::milliseconds timeout_;

  std::vector<std::uint8_t> frame_buffer_;
  std::vector<std::uint8_t> received_chunks_;

  bool active_ = false;
  bool have_recent_frame_id_ = false;
  std::uint32_t recent_frame_id_ = 0;

  bool have_bad_size_frame_id_ = false;
  std::uint32_t bad_size_frame_id_ = 0;

  std::uint32_t current_frame_id_ = 0;
  std::uint16_t current_total_chunks_ = 0;
  std::uint16_t received_count_ = 0;
  std::size_t current_chunk_payload_size_ = 0;
  std::chrono::steady_clock::time_point last_update_{};
};

}  // namespace bric

