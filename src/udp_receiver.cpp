#include "udp_receiver.hpp"

#include "led_display.hpp"
#include "utils.hpp"

#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cstring>
#include <iostream>
#include <sstream>

namespace bric {
namespace {

std::string sockaddrToIp(const sockaddr_in& address) {
  char buffer[INET_ADDRSTRLEN] = {};
  const char* result =
      inet_ntop(AF_INET, &address.sin_addr, buffer, sizeof(buffer));
  return result == nullptr ? "-" : std::string(result);
}

}  // namespace

UDPReceiver::UDPReceiver(const BricConfig& config, LEDDisplay& display)
    : config_(config),
      display_(display),
      reassembler_(config.wall_width, config.wall_height,
                   config.frame_timeout_ms),
      recv_buffer_(kMaxUdpPayloadSize),
      send_buffer_(kMaxUdpPayloadSize) {}

UDPReceiver::~UDPReceiver() { closeSocket(); }

bool UDPReceiver::openSocket() {
  closeSocket();

  socket_fd_ = socket(AF_INET, SOCK_DGRAM, 0);
  if (socket_fd_ < 0) {
    std::cerr << "socket() failed: " << std::strerror(errno) << "\n";
    return false;
  }

  int yes = 1;
  if (setsockopt(socket_fd_, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes)) != 0) {
    std::cerr << "setsockopt(SO_REUSEADDR) failed: " << std::strerror(errno)
              << "\n";
  }

  int requested_rcvbuf = config_.socket_rcvbuf;
  if (setsockopt(socket_fd_, SOL_SOCKET, SO_RCVBUF, &requested_rcvbuf,
                 sizeof(requested_rcvbuf)) != 0) {
    std::cerr << "setsockopt(SO_RCVBUF) failed: " << std::strerror(errno)
              << "\n";
  }

  timeval receive_timeout{};
  receive_timeout.tv_sec = 0;
  receive_timeout.tv_usec = 100000;
  if (setsockopt(socket_fd_, SOL_SOCKET, SO_RCVTIMEO, &receive_timeout,
                 sizeof(receive_timeout)) != 0) {
    std::cerr << "setsockopt(SO_RCVTIMEO) failed: " << std::strerror(errno)
              << "\n";
  }

  sockaddr_in bind_address{};
  bind_address.sin_family = AF_INET;
  bind_address.sin_port = htons(config_.listen_port);
  if (inet_pton(AF_INET, config_.listen_ip.c_str(), &bind_address.sin_addr) !=
      1) {
    std::cerr << "invalid listen IP: " << config_.listen_ip << "\n";
    return false;
  }

  if (bind(socket_fd_, reinterpret_cast<sockaddr*>(&bind_address),
           sizeof(bind_address)) != 0) {
    std::cerr << "bind(" << config_.listen_ip << ":" << config_.listen_port
              << ") failed: " << std::strerror(errno) << "\n";
    return false;
  }

  return true;
}

void UDPReceiver::run(const std::function<bool()>& should_stop) {
  if (socket_fd_ < 0 && !openSocket()) {
    return;
  }

  std::cout << "Listening on " << config_.listen_ip << ":"
            << config_.listen_port << "\n";
  last_stats_time_ = std::chrono::steady_clock::now();

  while (!should_stop()) {
    sockaddr_in peer{};
    socklen_t peer_len = sizeof(peer);
    const ssize_t received =
        recvfrom(socket_fd_, recv_buffer_.data(), recv_buffer_.size(), 0,
                 reinterpret_cast<sockaddr*>(&peer), &peer_len);
    const auto now = std::chrono::steady_clock::now();

    if (received < 0) {
      if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
        if (reassembler_.expireStale(now)) {
          ++stats_.incomplete_frames;
          ++stats_.dropped_frames;
        }
        maybePrintStats(now);
        continue;
      }
      std::cerr << "recvfrom() failed: " << std::strerror(errno) << "\n";
      continue;
    }

    stats_.packets += 1;
    stats_.bytes += static_cast<std::uint64_t>(received);
    stats_.last_sender_ip = sockaddrToIp(peer);

    PacketHeader header;
    const std::uint8_t* payload = nullptr;
    const ParseStatus parse_status =
        parsePacketHeader(recv_buffer_.data(), static_cast<std::size_t>(received),
                          &header, &payload);
    if (parse_status != ParseStatus::kOk) {
      ++stats_.bad_packets;
      maybePrintStats(now);
      continue;
    }

    if (header.packet_type == PacketType::kPing ||
        header.packet_type == PacketType::kInfoRequest) {
      handleControlPacket(header, peer, peer_len);
      maybePrintStats(now);
      continue;
    }

    const ReassemblerResult result =
        reassembler_.processPacket(header, payload, now);
    if (result.bad_packet) {
      ++stats_.bad_packets;
    }
    if (result.bad_size_frame) {
      ++stats_.bad_size_frames;
      ++stats_.dropped_frames;
    }
    if (result.dropped_incomplete) {
      ++stats_.incomplete_frames;
      ++stats_.dropped_frames;
    }
    if (result.completed) {
      ++stats_.completed_frames;
      display_.showFrame(result.frame_data, config_.wall_width,
                         config_.wall_height);
      ++stats_.displayed_frames;
    }

    maybePrintStats(now);
  }
}

void UDPReceiver::closeSocket() {
  if (socket_fd_ >= 0) {
    close(socket_fd_);
    socket_fd_ = -1;
  }
}

void UDPReceiver::maybePrintStats(std::chrono::steady_clock::time_point now) {
  const std::chrono::duration<double> elapsed = now - last_stats_time_;
  if (elapsed.count() < 1.0) {
    return;
  }

  const double seconds = elapsed.count();
  const double packets_per_second =
      static_cast<double>(stats_.packets - last_stats_packets_) / seconds;
  const double bytes_per_second =
      static_cast<double>(stats_.bytes - last_stats_bytes_) / seconds;
  const double displayed_fps =
      static_cast<double>(stats_.displayed_frames - last_stats_displayed_) /
      seconds;

  std::cout << "stats packets_per_second=" << packets_per_second
            << " bytes_per_second=" << bytes_per_second
            << " completed_frames=" << stats_.completed_frames
            << " displayed_fps=" << displayed_fps
            << " dropped_frames=" << stats_.dropped_frames
            << " incomplete_frames=" << stats_.incomplete_frames
            << " bad_packets=" << stats_.bad_packets
            << " bad_size_frames=" << stats_.bad_size_frames
            << " last_sender_ip=" << stats_.last_sender_ip << "\n";

  last_stats_time_ = now;
  last_stats_packets_ = stats_.packets;
  last_stats_bytes_ = stats_.bytes;
  last_stats_displayed_ = stats_.displayed_frames;
}

void UDPReceiver::handleControlPacket(const PacketHeader& header,
                                      const sockaddr_in& peer,
                                      socklen_t peer_len) {
  if (header.packet_type == PacketType::kPing) {
    sendControlResponse(PacketType::kPong, header.frame_id, "", peer,
                        peer_len);
  } else if (header.packet_type == PacketType::kInfoRequest) {
    sendControlResponse(PacketType::kInfoResponse, header.frame_id,
                        infoJsonForPeer(peer), peer, peer_len);
  }
}

void UDPReceiver::sendControlResponse(PacketType type, std::uint32_t frame_id,
                                      const std::string& payload,
                                      const sockaddr_in& peer,
                                      socklen_t peer_len) {
  if (socket_fd_ < 0 || payload.size() > 65535U ||
      payload.size() + kHeaderSize > send_buffer_.size()) {
    return;
  }

  PacketHeader response;
  response.packet_type = type;
  response.header_size = kHeaderSize;
  response.frame_id = frame_id;
  response.frame_width = static_cast<std::uint16_t>(config_.wall_width);
  response.frame_height = static_cast<std::uint16_t>(config_.wall_height);
  response.chunk_index = 0;
  response.total_chunks = 1;
  response.payload_size = static_cast<std::uint16_t>(payload.size());

  writePacketHeader(response, send_buffer_.data());
  if (!payload.empty()) {
    std::memcpy(send_buffer_.data() + kHeaderSize, payload.data(),
                payload.size());
  }
  sendto(socket_fd_, send_buffer_.data(), kHeaderSize + payload.size(), 0,
         reinterpret_cast<const sockaddr*>(&peer), peer_len);
}

std::string UDPReceiver::infoJsonForPeer(const sockaddr_in& peer) const {
  std::ostringstream out;
  const std::string peer_ip = sockaddrToIp(peer);
  std::string local_ip = getLocalIpForPeer(peer_ip);
  if (local_ip.empty()) {
    local_ip = getInterfaceIPv4("eth0");
  }

  out << "{"
      << "\"type\":\"BRIC_TILE_RESPONSE\","
      << "\"hostname\":\"" << jsonEscape(config_.tile_name) << "\","
      << "\"mac\":\"" << jsonEscape(config_.tile_mac) << "\","
      << "\"ip\":\"" << jsonEscape(local_ip) << "\","
      << "\"listen_port\":" << config_.listen_port << ","
      << "\"wall_width\":" << config_.wall_width << ","
      << "\"wall_height\":" << config_.wall_height << ","
      << "\"panel_rows\":" << config_.panel_rows << ","
      << "\"panel_cols\":" << config_.panel_cols << ","
      << "\"panel_chain\":" << config_.panel_chain << ","
      << "\"panel_parallel\":" << config_.panel_parallel << ","
      << "\"brightness\":" << config_.brightness << ","
      << "\"hardware_mapping\":\"" << jsonEscape(config_.hardware_mapping)
      << "\","
      << "\"pixel_mapping\":\"" << jsonEscape(config_.pixel_mapping) << "\","
      << "\"slowdown_gpio\":" << config_.slowdown_gpio << ","
      << "\"version\":\"bric-tile-receiver-v0.1.0\""
      << "}";
  return out.str();
}

}  // namespace bric
