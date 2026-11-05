// P5-20: servidor HTTP de la cámara.
//
// Basado en el `app_httpd.cpp` del kit, que a su vez viene del ejemplo CameraWebServer de
// Espressif (Apache-2.0). Se conservan /capture (puerto 80) y /stream (puerto 81) tal como los
// usan src/captura y el lazo en vivo. Cambios de P5-20:
//  - Sin /go, /back, /left, /right, /stop, /ledon ni /ledoff: los motores solo se mueven con
//    órdenes UDP con paro automático (ordenes.cpp).
//  - La página / ya no tiene botones de motor.
//  - El stream ya no imprime una línea "MJPG: ..." por cuadro en el Monitor Serie, para que se
//    lean las órdenes. Con DEPURAR_STREAM en 1 vuelve a imprimirlas.

#include "Arduino.h"
#include "esp_camera.h"
#include "esp_http_server.h"
#include "esp_timer.h"

#define DEPURAR_STREAM 0

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static httpd_handle_t stream_httpd = NULL;
static httpd_handle_t camera_httpd = NULL;

static esp_err_t capture_handler(httpd_req_t* req) {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  esp_err_t res = httpd_resp_send(req, (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

static esp_err_t stream_handler(httpd_req_t* req) {
  char part_buf[64];
  esp_err_t res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;
#if DEPURAR_STREAM
  int64_t ultimo = esp_timer_get_time();
#endif
  while (true) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Camera capture failed");
      return ESP_FAIL;
    }
    size_t hlen = snprintf(part_buf, sizeof(part_buf), _STREAM_PART, fb->len);
    res = httpd_resp_send_chunk(req, part_buf, hlen);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
#if DEPURAR_STREAM
    int64_t ahora = esp_timer_get_time();
    Serial.printf("MJPG: %uB %ums\n", (unsigned)fb->len, (unsigned)((ahora - ultimo) / 1000));
    ultimo = ahora;
#endif
    esp_camera_fb_return(fb);
    if (res != ESP_OK) break;  // el cliente cerró
  }
  return res;
}

static esp_err_t index_handler(httpd_req_t* req) {
  static const char pagina[] =
      "<!doctype html><html><head><meta charset=utf-8>"
      "<meta name=viewport content='width=device-width'><title>Mini Tesla P5</title></head>"
      "<body style='font-family:sans-serif;text-align:center;background:#111;color:#eee'>"
      "<h2>Mini Tesla P5</h2>"
      "<p>Los motores solo se mueven con &oacute;rdenes UDP (puerto 4210, protocolo P5C1)."
      "<br>Ver docs/carro/protocolo.md.</p>"
      "<p><a style='color:#9cf' href='/capture'>/capture</a></p>"
      "<img id=v style='max-width:100%'>"
      "<script>document.getElementById('v').src="
      "location.protocol+'//'+location.hostname+':81/stream';</script>"
      "</body></html>";
  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, pagina, sizeof(pagina) - 1);
}

void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();

  httpd_uri_t index_uri = {.uri = "/", .method = HTTP_GET, .handler = index_handler, .user_ctx = NULL};
  httpd_uri_t capture_uri = {
      .uri = "/capture", .method = HTTP_GET, .handler = capture_handler, .user_ctx = NULL};
  httpd_uri_t stream_uri = {
      .uri = "/stream", .method = HTTP_GET, .handler = stream_handler, .user_ctx = NULL};

  Serial.printf("Servidor web en el puerto %d\n", config.server_port);
  if (httpd_start(&camera_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &index_uri);
    httpd_register_uri_handler(camera_httpd, &capture_uri);
  }

  config.server_port += 1;
  config.ctrl_port += 1;
  Serial.printf("Stream en el puerto %d\n", config.server_port);
  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
  }
}
