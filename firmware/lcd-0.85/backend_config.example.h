#pragma once

// Copy to backend_config.h (gitignored) and set this Mac's LAN IP.
// Find it with: ipconfig getifaddr en0

#define BACKEND_SCHEME "http"
#define BACKEND_HOST "192.168.68.80"
#define BACKEND_PORT 8765

// Used only when the laptop helper is not found on the LAN.
#define BACKEND_CLOUD_SCHEME "https"
#define BACKEND_CLOUD_HOST "voxpin-helper.fly.dev"
#define BACKEND_CLOUD_PORT 443
