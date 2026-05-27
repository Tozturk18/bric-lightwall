#include "bric_config.hpp"
#include "led_display.hpp"
#include "udp_receiver.hpp"

#include <csignal>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <string>
#include <thread>

namespace {

volatile std::sig_atomic_t g_should_stop = 0;

void handleSignal(int) { g_should_stop = 1; }

bool shouldStop() { return g_should_stop != 0; }

void printUsage(const char* argv0) {
  std::cout << "Usage: " << argv0
            << " [--config PATH] [--test-pattern SECONDS]\n";
}

}  // namespace

int main(int argc, char** argv) {
  std::cout << std::unitbuf;
  std::cerr << std::unitbuf;

  std::string config_path = "/etc/bric-lightwall/tile.env";
  int test_pattern_seconds = 0;

  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--config" && i + 1 < argc) {
      config_path = argv[++i];
    } else if (arg == "--test-pattern" && i + 1 < argc) {
      test_pattern_seconds = std::atoi(argv[++i]);
    } else if (arg == "--help" || arg == "-h") {
      printUsage(argv[0]);
      return 0;
    } else {
      std::cerr << "Unknown argument: " << arg << "\n";
      printUsage(argv[0]);
      return 2;
    }
  }

  std::signal(SIGINT, handleSignal);
  std::signal(SIGTERM, handleSignal);

  try {
    const bric::BricConfig config = bric::loadConfig(config_path);
    std::cout << "BRIC tile receiver v0.1.0\n";
    std::cout << bric::configSummary(config) << "\n";

    bric::LEDDisplay display(config);

    if (test_pattern_seconds > 0) {
      display.showTestPattern();
      std::this_thread::sleep_for(
          std::chrono::seconds(test_pattern_seconds));
      display.clear();
      return 0;
    }

    if (config.idle_pattern == "test") {
      display.showTestPattern();
    } else {
      display.clear();
    }

    bric::UDPReceiver receiver(config, display);
    receiver.run(shouldStop);
    display.clear();
  } catch (const std::exception& error) {
    std::cerr << "fatal: " << error.what() << "\n";
    return 1;
  }

  return 0;
}
