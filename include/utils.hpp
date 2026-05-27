#pragma once

#include <cstdint>
#include <string>

namespace bric {

std::string trim(const std::string& value);
bool parseInt(const std::string& text, int* out);
int clampInt(int value, int min_value, int max_value);
std::string getHostname();
std::string getInterfaceMac(const std::string& interface_name);
std::string getInterfaceIPv4(const std::string& interface_name);
std::string getLocalIpForPeer(const std::string& peer_ip);
std::string jsonEscape(const std::string& value);

}  // namespace bric

