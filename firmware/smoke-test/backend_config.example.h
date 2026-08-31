#pragma once

// Copy to backend_config.h (gitignored) and set this Mac's LAN IP.
// Find it with: ipconfig getifaddr en0
// The voice-notes backend listens on this port.

#define BACKEND_HOST "192.168.68.80"
#define BACKEND_PORT 8765
