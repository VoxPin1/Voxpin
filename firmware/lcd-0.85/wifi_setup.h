#pragma once

// True when + is held at boot. Waits for release so it doesn't also send SOS.
bool wifi_setup_requested(void);

// Runs the open "VoxPin-Setup" hotspot with a captive page for picking a Wi-Fi.
// Returns true once the pin has joined and saved a network, or false after two
// minutes with no phone connected so the caller can retry known networks.
bool wifi_setup_run(void (*status)(const char *text));

// Asks loop() to open the setup hotspot while the pin is running.
void wifi_setup_request(void);
// True from a request until setup has finished and known networks are rejoined.
// Background reconnects must stay off the radio meanwhile.
bool wifi_setup_active(void);
// Called from loop(): runs a requested setup, then rejoins like boot does.
void wifi_setup_poll(void (*status)(const char *text));
