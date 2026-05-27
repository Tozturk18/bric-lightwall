#pragma once

#include <arpa/inet.h>

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace bric {

constexpr char kMagic[4] = {'B', 'R', 'I', 'C'};
constexpr char kBrcpMagic[4] = {'B', 'R', 'C', 'P'};
constexpr std::uint8_t kProtocolVersion = 1;
constexpr std::uint16_t kHeaderSize = 28;
constexpr std::uint16_t kBrcpHeaderSize = 18;
constexpr std::size_t kDefaultChunkPayloadSize = 1024;
constexpr std::size_t kMaxUdpPayloadSize = 65507;
constexpr std::size_t kMaxFrameBytes = 64U * 1024U * 1024U;
constexpr std::uint16_t kMaxChunksPerFrame = 4096;

enum class PacketType : std::uint8_t {
  kFrameChunk = 1,
  kFullFrame = 2,
  kPing = 3,
  kPong = 4,
  kInfoRequest = 5,
  kInfoResponse = 6,
};

#pragma pack(push, 1)
struct WirePacketHeader {
  char magic[4];
  std::uint8_t version;
  std::uint8_t packet_type;
  std::uint16_t header_size;
  std::uint32_t frame_id;
  std::uint16_t frame_width;
  std::uint16_t frame_height;
  std::uint16_t chunk_index;
  std::uint16_t total_chunks;
  std::uint16_t payload_size;
  std::uint16_t flags;
  std::uint32_t reserved;
};
#pragma pack(pop)

static_assert(sizeof(WirePacketHeader) == kHeaderSize,
              "BRIC UDP header must remain 28 bytes");

#pragma pack(push, 1)
struct BrcpWirePacketHeader {
  char magic[4];
  std::uint16_t frame_width;
  std::uint16_t frame_height;
  std::uint32_t frame_number;
  std::uint16_t chunk_index;
  std::uint16_t total_chunks;
  std::uint16_t payload_length;
};
#pragma pack(pop)

static_assert(sizeof(BrcpWirePacketHeader) == kBrcpHeaderSize,
              "BRCP UDP header must remain 18 bytes");

struct PacketHeader {
  std::uint8_t version = 0;
  PacketType packet_type = PacketType::kFrameChunk;
  std::uint16_t header_size = 0;
  std::uint32_t frame_id = 0;
  std::uint16_t frame_width = 0;
  std::uint16_t frame_height = 0;
  std::uint16_t chunk_index = 0;
  std::uint16_t total_chunks = 0;
  std::uint16_t payload_size = 0;
  std::uint16_t flags = 0;
  std::uint32_t reserved = 0;
};

enum class ParseStatus {
  kOk,
  kTooSmall,
  kBadMagic,
  kBadVersion,
  kBadPacketType,
  kBadHeaderSize,
  kTruncatedPayload,
};

inline ParseStatus parseBrcpPacketHeader(const std::uint8_t* data,
                                         std::size_t size, PacketHeader* out,
                                         const std::uint8_t** payload) {
  if (size < sizeof(BrcpWirePacketHeader)) {
    return ParseStatus::kTooSmall;
  }

  BrcpWirePacketHeader wire{};
  std::memcpy(&wire, data, sizeof(wire));

  if (std::memcmp(wire.magic, kBrcpMagic, sizeof(kBrcpMagic)) != 0) {
    return ParseStatus::kBadMagic;
  }

  const std::uint16_t payload_size = ntohs(wire.payload_length);
  if (static_cast<std::size_t>(payload_size) >
      size - sizeof(BrcpWirePacketHeader)) {
    return ParseStatus::kTruncatedPayload;
  }

  out->version = kProtocolVersion;
  out->packet_type = PacketType::kFrameChunk;
  out->header_size = kBrcpHeaderSize;
  out->frame_id = ntohl(wire.frame_number);
  out->frame_width = ntohs(wire.frame_width);
  out->frame_height = ntohs(wire.frame_height);
  out->chunk_index = ntohs(wire.chunk_index);
  out->total_chunks = ntohs(wire.total_chunks);
  out->payload_size = payload_size;
  out->flags = 0;
  out->reserved = 0;
  *payload = data + sizeof(BrcpWirePacketHeader);
  return ParseStatus::kOk;
}

inline bool isKnownPacketType(std::uint8_t value) {
  return value >= static_cast<std::uint8_t>(PacketType::kFrameChunk) &&
         value <= static_cast<std::uint8_t>(PacketType::kInfoResponse);
}

inline ParseStatus parsePacketHeader(const std::uint8_t* data, std::size_t size,
                                     PacketHeader* out,
                                     const std::uint8_t** payload) {
  if (size < sizeof(WirePacketHeader)) {
    if (size >= sizeof(BrcpWirePacketHeader) &&
        std::memcmp(data, kBrcpMagic, sizeof(kBrcpMagic)) == 0) {
      return parseBrcpPacketHeader(data, size, out, payload);
    }
    return ParseStatus::kTooSmall;
  }

  if (std::memcmp(data, kBrcpMagic, sizeof(kBrcpMagic)) == 0) {
    return parseBrcpPacketHeader(data, size, out, payload);
  }

  WirePacketHeader wire{};
  std::memcpy(&wire, data, sizeof(wire));

  if (std::memcmp(wire.magic, kMagic, sizeof(kMagic)) != 0) {
    return ParseStatus::kBadMagic;
  }
  if (wire.version != kProtocolVersion) {
    return ParseStatus::kBadVersion;
  }
  if (!isKnownPacketType(wire.packet_type)) {
    return ParseStatus::kBadPacketType;
  }

  const std::uint16_t header_size = ntohs(wire.header_size);
  if (header_size < sizeof(WirePacketHeader) || header_size > size) {
    return ParseStatus::kBadHeaderSize;
  }

  const std::uint16_t payload_size = ntohs(wire.payload_size);
  if (static_cast<std::size_t>(payload_size) > size - header_size) {
    return ParseStatus::kTruncatedPayload;
  }

  out->version = wire.version;
  out->packet_type = static_cast<PacketType>(wire.packet_type);
  out->header_size = header_size;
  out->frame_id = ntohl(wire.frame_id);
  out->frame_width = ntohs(wire.frame_width);
  out->frame_height = ntohs(wire.frame_height);
  out->chunk_index = ntohs(wire.chunk_index);
  out->total_chunks = ntohs(wire.total_chunks);
  out->payload_size = payload_size;
  out->flags = ntohs(wire.flags);
  out->reserved = ntohl(wire.reserved);
  *payload = data + header_size;
  return ParseStatus::kOk;
}

inline void writePacketHeader(const PacketHeader& header, std::uint8_t* out) {
  WirePacketHeader wire{};
  std::memcpy(wire.magic, kMagic, sizeof(kMagic));
  wire.version = kProtocolVersion;
  wire.packet_type = static_cast<std::uint8_t>(header.packet_type);
  wire.header_size = htons(header.header_size);
  wire.frame_id = htonl(header.frame_id);
  wire.frame_width = htons(header.frame_width);
  wire.frame_height = htons(header.frame_height);
  wire.chunk_index = htons(header.chunk_index);
  wire.total_chunks = htons(header.total_chunks);
  wire.payload_size = htons(header.payload_size);
  wire.flags = htons(header.flags);
  wire.reserved = htonl(header.reserved);
  std::memcpy(out, &wire, sizeof(wire));
}

}  // namespace bric
