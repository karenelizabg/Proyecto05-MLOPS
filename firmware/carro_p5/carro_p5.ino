// P5-20: firmware del carro (ESP32-CAM AI Thinker + L298N).
//
// Base: `ESP32CAM_Car` del kit, con los cambios de datos/CARRO.md (VGA, XCLK a 10 MHz,
// vflip + hmirror, /capture, reinicio si la foto de prueba falla). Lo nuevo de P5-20:
//  - Los pines de motor se ponen en bajo antes que todo.
//  - Los motores solo se mueven con órdenes UDP del protocolo v1 (ordenes.cpp), con paro
//    automático. Se quitaron /go, /back, /left, /right y /stop del kit: no frenaban solos.
//  - La red y la clave van en secretos.h, que no se sube (ver secretos.h.ejemplo).
//
// Cargar: ver firmware/carro_p5/README.md.

#include <WiFi.h>

#include "esp_camera.h"
#include "ordenes.h"

#if __has_include("secretos.h")
#include "secretos.h"
#else
#error "Falta firmware/carro_p5/secretos.h: copia secretos.h.ejemplo y pon tu red."
#endif

// Cámara AI Thinker.
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

// Cuenta los reinicios por foto de prueba fallida; sobrevive a ESP.restart().
RTC_NOINIT_ATTR int reinicios_camara;

void startCameraServer();

static bool iniciarCamara() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 10000000;  // a 20 MHz el sensor no entregaba cuadros
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;  // 640x480, la resolución del detector
  config.jpeg_quality = 10;
  config.fb_count = psramFound() ? 2 : 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return false;
  }
  sensor_t* s = esp_camera_sensor_get();
  s->set_framesize(s, FRAMESIZE_VGA);
  s->set_vflip(s, 1);  // la cámara va de cabeza: vflip + hmirror = giro de 180°
  s->set_hmirror(s, 1);
  return true;
}

// Foto de prueba; si falla, reinicia (máximo 3 veces seguidas).
static void fotoDePrueba() {
  if (esp_reset_reason() != ESP_RST_SW) reinicios_camara = 0;
  for (int i = 0; i < 3; i++) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (fb) {
      esp_camera_fb_return(fb);
      if (reinicios_camara > 0) Serial.printf("Camara lista tras %d reinicio(s)\n", reinicios_camara);
      reinicios_camara = 0;
      return;
    }
    delay(200);
  }
  if (reinicios_camara < 3) {
    reinicios_camara++;
    Serial.printf("Foto de prueba fallo; reiniciando (%d de 3)\n", reinicios_camara);
    delay(500);
    ESP.restart();
  }
  Serial.println("Foto de prueba fallo tras 3 reinicios; se sigue sin camara");
}

void setup() {
  motoresSeguros();  // primero que todo: motores en bajo
  Serial.begin(115200);
  Serial.println();
  Serial.println("Mini Tesla P5 - firmware carro_p5 (protocolo P5C1)");

  if (iniciarCamara()) {
    fotoDePrueba();
  } else {
    Serial.println("Sin camara: se sigue para poder recibir STOP y diagnosticar por WiFi");
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // sin ahorro de energía: menos retraso en las órdenes
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_CLAVE);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.println("WiFi connected");

  startCameraServer();
  iniciarOrdenes();

  Serial.print("Camera Ready! Use 'http://");
  Serial.print(WiFi.localIP());
  Serial.println("' to connect");
}

void loop() {
  delay(1000);  // todo pasa en las tareas del servidor y de órdenes
}
