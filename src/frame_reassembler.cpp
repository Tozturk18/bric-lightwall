#include "frame_reassembler.hpp"

#include <algorithm>
#include <cstring>
#include <limits>

namespace bric {
namespace {

bool checkedFrameBytes(std::uint16_t width, std::uint16_t height,
                       std::size_t* out) {
  if (width == 0 || height == 0) {
    return false;
  }

  const std::size_t bytes =
      static_cast<std::size_t>(width) * static_cast<std::size_t>(height) * 3U;
  if (bytes == 0 || bytes > kMaxFrameBytes) {
    return false;
  }

  *out = bytes;
  return true;
}

}  // namespace

FrameReassembler::FrameReassembler(int display_width, int display_height,
                                   int timeout_ms)
    : display_width_(display_width),
      display_height_(display_height),
      frame_bytes_(static_cast<std::size_t>(display_width) *
                   static_cast<std::size_t>(display_height) * 3U),
      timeout_(std::chrono::milliseconds(timeout_ms)),
      frame_buffer_(frame_bytes_),
      received_chunks_(kMaxChunksPerFrame, 0) {}

ReassemblerResult FrameReassembler::processPacket(
    const PacketHeader& header, const std::uint8_t* payload,
    std::chrono::steady_clock::time_point now) {
  ReassemblerResult result;
  result.frame_id = header.frame_id;

  if (expireStale(now)) {
    result.dropped_incomplete = true;
  }

  const bool is_frame_packet =
      header.packet_type == PacketType::kFrameChunk ||
      header.packet_type == PacketType::kFullFrame;
  if (!is_frame_packet) {
    result.ignored_stale = true;
    return result;
  }

  std::size_t incoming_frame_bytes = 0;
  if (!checkedFrameBytes(header.frame_width, header.frame_height,
                         &incoming_frame_bytes) ||
      header.total_chunks == 0 || header.total_chunks > kMaxChunksPerFrame ||
      header.chunk_index >= header.total_chunks || header.payload_size == 0 ||
      payload == nullptr) {
    result.bad_packet = true;
    return result;
  }

  if (header.packet_type == PacketType::kFullFrame &&
      (header.total_chunks != 1 || header.chunk_index != 0 ||
       header.payload_size != incoming_frame_bytes)) {
    result.bad_packet = true;
    return result;
  }

  if (active_) {
    if (header.frame_id != current_frame_id_) {
      if (!isNewerFrame(header.frame_id, current_frame_id_)) {
        result.ignored_stale = true;
        return result;
      }
      dropActiveFrame();
      result.dropped_incomplete = true;
    } else if (header.total_chunks != current_total_chunks_) {
      result.bad_packet = true;
      return result;
    }
  } else if (have_recent_frame_id_ &&
             !isNewerFrame(header.frame_id, recent_frame_id_)) {
    result.ignored_stale = true;
    return result;
  }

  if (header.frame_width != display_width_ ||
      header.frame_height != display_height_) {
    if (!have_recent_frame_id_ ||
        isNewerFrame(header.frame_id, recent_frame_id_)) {
      recent_frame_id_ = header.frame_id;
      have_recent_frame_id_ = true;
    }
    result.bad_size_frame = markBadSizeFrame(header.frame_id);
    return result;
  }

  if (!active_ && !startFrame(header, now)) {
    result.bad_packet = true;
    return result;
  }

  std::size_t expected_payload_size = 0;
  if (!inferOrValidateChunkPayloadSize(header, &expected_payload_size)) {
    result.bad_packet = true;
    return result;
  }

  if (header.payload_size != expected_payload_size) {
    result.bad_packet = true;
    return result;
  }

  const std::size_t offset =
      static_cast<std::size_t>(header.chunk_index) *
      current_chunk_payload_size_;
  if (offset + header.payload_size > frame_buffer_.size()) {
    result.bad_packet = true;
    return result;
  }

  last_update_ = now;

  if (received_chunks_[header.chunk_index]) {
    return result;
  }

  std::memcpy(frame_buffer_.data() + offset, payload, header.payload_size);
  received_chunks_[header.chunk_index] = 1;
  ++received_count_;

  if (received_count_ == current_total_chunks_) {
    result.completed = true;
    result.frame_data = frame_buffer_.data();
    result.frame_size = frame_buffer_.size();
    recent_frame_id_ = current_frame_id_;
    have_recent_frame_id_ = true;
    active_ = false;
  }

  return result;
}

bool FrameReassembler::expireStale(
    std::chrono::steady_clock::time_point now) {
  if (!active_) {
    return false;
  }
  if (now - last_update_ <= timeout_) {
    return false;
  }
  dropActiveFrame();
  return true;
}

bool FrameReassembler::startFrame(
    const PacketHeader& header, std::chrono::steady_clock::time_point now) {
  if (header.total_chunks == 0 ||
      header.total_chunks > received_chunks_.size()) {
    return false;
  }

  std::fill_n(received_chunks_.begin(), header.total_chunks, 0);
  current_frame_id_ = header.frame_id;
  current_total_chunks_ = header.total_chunks;
  received_count_ = 0;
  current_chunk_payload_size_ = 0;
  last_update_ = now;
  active_ = true;
  recent_frame_id_ = header.frame_id;
  have_recent_frame_id_ = true;
  return true;
}

bool FrameReassembler::inferOrValidateChunkPayloadSize(
    const PacketHeader& header, std::size_t* expected_payload_size) {
  std::size_t inferred_chunk_size = current_chunk_payload_size_;

  if (inferred_chunk_size == 0) {
    if (header.total_chunks == 1) {
      inferred_chunk_size = frame_bytes_;
    } else if (header.chunk_index == header.total_chunks - 1) {
      if (header.payload_size > frame_bytes_) {
        return false;
      }
      const std::size_t non_final_chunks = header.total_chunks - 1;
      const std::size_t remaining = frame_bytes_ - header.payload_size;
      if (non_final_chunks == 0 || remaining % non_final_chunks != 0) {
        return false;
      }
      inferred_chunk_size = remaining / non_final_chunks;
    } else {
      inferred_chunk_size = header.payload_size;
    }

    if (inferred_chunk_size == 0 || inferred_chunk_size > kMaxUdpPayloadSize) {
      return false;
    }

    const std::size_t expected_chunks =
        (frame_bytes_ + inferred_chunk_size - 1) / inferred_chunk_size;
    if (expected_chunks != header.total_chunks) {
      return false;
    }
    current_chunk_payload_size_ = inferred_chunk_size;
  }

  if (header.chunk_index == header.total_chunks - 1) {
    const std::size_t last_offset =
        static_cast<std::size_t>(header.chunk_index) *
        current_chunk_payload_size_;
    if (last_offset >= frame_bytes_) {
      return false;
    }
    *expected_payload_size = frame_bytes_ - last_offset;
  } else {
    *expected_payload_size = current_chunk_payload_size_;
  }

  return *expected_payload_size <= std::numeric_limits<std::uint16_t>::max();
}

void FrameReassembler::dropActiveFrame() {
  if (active_) {
    recent_frame_id_ = current_frame_id_;
    have_recent_frame_id_ = true;
    active_ = false;
  }
}

bool FrameReassembler::isNewerFrame(std::uint32_t candidate,
                                    std::uint32_t reference) const {
  return static_cast<std::int32_t>(candidate - reference) > 0;
}

bool FrameReassembler::markBadSizeFrame(std::uint32_t frame_id) {
  if (have_bad_size_frame_id_ && frame_id == bad_size_frame_id_) {
    return false;
  }
  bad_size_frame_id_ = frame_id;
  have_bad_size_frame_id_ = true;
  return true;
}

}  // namespace bric
