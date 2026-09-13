#pragma once

#include <HTTPClient.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <stdio.h>
#include <string.h>

#include "backend_config.h"

#ifndef BACKEND_SCHEME
#define BACKEND_SCHEME "http"
#endif

#ifndef BACKEND_CLOUD_SCHEME
#define BACKEND_CLOUD_SCHEME "https"
#endif
#ifndef BACKEND_CLOUD_HOST
#define BACKEND_CLOUD_HOST ""
#endif
#ifndef BACKEND_CLOUD_PORT
#define BACKEND_CLOUD_PORT 443
#endif

extern char g_backend_host[64];
extern int g_backend_port;
extern char g_backend_scheme[8];

void backend_set_target(const char *host, int port, const char *scheme);
bool backend_discover(uint32_t timeout_ms);
bool backend_fallback_cloud();

inline void backend_make_url(char *out, size_t out_len, const char *path)
{
  if ((g_backend_port == 443 && strcmp(g_backend_scheme, "https") == 0) ||
      (g_backend_port == 80 && strcmp(g_backend_scheme, "http") == 0)) {
    snprintf(out, out_len, "%s://%s%s", g_backend_scheme, g_backend_host, path);
  } else {
    snprintf(out, out_len, "%s://%s:%d%s", g_backend_scheme, g_backend_host, g_backend_port, path);
  }
}

inline bool backend_http_begin(HTTPClient &http, WiFiClientSecure &tls, WiFiClient &plain,
                               const char *path)
{
  char url[160];
  backend_make_url(url, sizeof(url), path);
  if (strcmp(g_backend_scheme, "https") == 0) {
    tls.setInsecure();
    return http.begin(tls, url);
  }
  return http.begin(plain, url);
}
