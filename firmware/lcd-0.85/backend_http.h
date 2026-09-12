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

inline void backend_make_url(char *out, size_t out_len, const char *path)
{
  if ((BACKEND_PORT == 443 && strcmp(BACKEND_SCHEME, "https") == 0) ||
      (BACKEND_PORT == 80 && strcmp(BACKEND_SCHEME, "http") == 0)) {
    snprintf(out, out_len, "%s://%s%s", BACKEND_SCHEME, BACKEND_HOST, path);
  } else {
    snprintf(out, out_len, "%s://%s:%d%s", BACKEND_SCHEME, BACKEND_HOST, BACKEND_PORT, path);
  }
}

inline bool backend_http_begin(HTTPClient &http, WiFiClientSecure &tls, WiFiClient &plain,
                               const char *path)
{
  char url[160];
  backend_make_url(url, sizeof(url), path);
  if (strcmp(BACKEND_SCHEME, "https") == 0) {
    tls.setInsecure();
    return http.begin(tls, url);
  }
  return http.begin(plain, url);
}
