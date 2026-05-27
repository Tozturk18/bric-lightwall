#pragma once

#include "bric_config.hpp"
#include "frame_reassembler.hpp"

#include <chrono>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace bric {

class LEDDisplay;

struct ReceiverStats {
  std::uint64_t packets = 0;
  std::uint64_t bytes = 0;
  std::uint64_t completed_frames = 0;
  std::uint64_t displayed_frames = 0;
  std::uint64_t dropped_frames = 0;
  std::uint64_t incomplete_frames = 0;
  std::uint64_t bad_packets = 0;
  std::uint64_t bad_size_frames = 0;
  std::string last_sender_ip = "-";
};

class UDPReceiver {
 public:
  UDPReceiver(const BricConfig& config, LEDDisplay& display);
  ~UDPReceiver();

  UDPReceiver(const UDPReceiver&) = delete;
  UDPReceiver& operator=(const UDPReceiver&) = delete;

  bool openSocket();
  void run(const std::function<bool()>& should_stop);

 private:
  void closeSocket();
  void maybePrintStats(std::chrono::steady_clock::time_point now);
  void handleControlPacket(const PacketHeader& header, const sockaddr_in& peer,
                           socklen_t peer_len);
  void sendControlResponse(PacketType type, std::uint32_t frame_id,
                           const std::string& payload,
                           const sockaddr_in& peer, socklen_t peer_len);
  std::string infoJsonForPeer(const sockaddr_in& peer) const;

  const BricConfig& config_;
  LEDDisplay& display_;
  FrameReassembler reassembler_;
  int socket_fd_ = -1;
  std::vector<std::uint8_t> recv_buffer_;
  std::vector<std::uint8_t> send_buffer_;
  ReceiverStats stats_;

  std::chrono::steady_clock::time_point last_stats_time_{};
  std::uint64_t last_stats_packets_ = 0;
  std::uint64_t last_stats_bytes_ = 0;
  std::uint64_t last_stats_displayed_ = 0;
};

}  // namespace bric

