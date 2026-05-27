#include "utils.hpp"

#include <arpa/inet.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <unistd.h>

#include <algorithm>
#include <charconv>
#include <cctype>
#include <fstream>
#include <sstream>

namespace bric {

std::string trim(const std::string& value) {
  const auto begin =
      std::find_if_not(value.begin(), value.end(), [](unsigned char ch) {
        return std::isspace(ch) != 0;
      });
  const auto end =
      std::find_if_not(value.rbegin(), value.rend(), [](unsigned char ch) {
        return std::isspace(ch) != 0;
      }).base();
  if (begin >= end) {
    return "";
  }
  return std::string(begin, end);
}

bool parseInt(const std::string& text, int* out) {
  const std::string clean = trim(text);
  if (clean.empty()) {
    return false;
  }

  int value = 0;
  const char* begin = clean.data();
  const char* end = clean.data() + clean.size();
  const auto result = std::from_chars(begin, end, value);
  if (result.ec != std::errc() || result.ptr != end) {
    return false;
  }

  *out = value;
  return true;
}

int clampInt(int value, int min_value, int max_value) {
  return std::max(min_value, std::min(value, max_value));
}

std::string getHostname() {
  char buffer[256] = {};
  if (gethostname(buffer, sizeof(buffer) - 1) != 0) {
    return "";
  }
  return std::string(buffer);
}

std::string getInterfaceMac(const std::string& interface_name) {
  std::ifstream input("/sys/class/net/" + interface_name + "/address");
  std::string mac;
  std::getline(input, mac);
  return trim(mac);
}

std::string getInterfaceIPv4(const std::string& interface_name) {
  ifaddrs* ifaddr = nullptr;
  if (getifaddrs(&ifaddr) != 0) {
    return "";
  }

  std::string result;
  for (ifaddrs* current = ifaddr; current != nullptr; current = current->ifa_next) {
    if (current->ifa_addr == nullptr || current->ifa_addr->sa_family != AF_INET ||
        interface_name != current->ifa_name) {
      continue;
    }

    char address[INET_ADDRSTRLEN] = {};
    const auto* sin =
        reinterpret_cast<const sockaddr_in*>(current->ifa_addr);
    if (inet_ntop(AF_INET, &sin->sin_addr, address, sizeof(address)) !=
        nullptr) {
      result = address;
      break;
    }
  }

  freeifaddrs(ifaddr);
  return result;
}

std::string getLocalIpForPeer(const std::string& peer_ip) {
  int fd = socket(AF_INET, SOCK_DGRAM, 0);
  if (fd < 0) {
    return "";
  }

  sockaddr_in peer{};
  peer.sin_family = AF_INET;
  peer.sin_port = htons(9);
  if (inet_pton(AF_INET, peer_ip.c_str(), &peer.sin_addr) != 1) {
    close(fd);
    return "";
  }

  std::string result;
  if (connect(fd, reinterpret_cast<sockaddr*>(&peer), sizeof(peer)) == 0) {
    sockaddr_in local{};
    socklen_t local_len = sizeof(local);
    if (getsockname(fd, reinterpret_cast<sockaddr*>(&local), &local_len) == 0) {
      char address[INET_ADDRSTRLEN] = {};
      if (inet_ntop(AF_INET, &local.sin_addr, address, sizeof(address)) !=
          nullptr) {
        result = address;
      }
    }
  }

  close(fd);
  return result;
}

std::string jsonEscape(const std::string& value) {
  std::ostringstream out;
  for (const char ch : value) {
    switch (ch) {
      case '\\':
        out << "\\\\";
        break;
      case '"':
        out << "\\\"";
        break;
      case '\b':
        out << "\\b";
        break;
      case '\f':
        out << "\\f";
        break;
      case '\n':
        out << "\\n";
        break;
      case '\r':
        out << "\\r";
        break;
      case '\t':
        out << "\\t";
        break;
      default:
        if (static_cast<unsigned char>(ch) < 0x20) {
          out << "\\u00";
          const char* hex = "0123456789abcdef";
          out << hex[(ch >> 4) & 0x0f] << hex[ch & 0x0f];
        } else {
          out << ch;
        }
        break;
    }
  }
  return out.str();
}

}  // namespace bric

