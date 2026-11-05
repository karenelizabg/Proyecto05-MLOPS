// P5-20: órdenes PC -> carro por UDP (protocolo v1).
//
// Repite en C++ las reglas de `Placa` (src/carro/protocolo.py), que es el modelo de referencia,
// y docs/carro/protocolo.md. Si cambian, se cambian los tres en el mismo PR.
//
// Seguridad:
//  - Todo rechazo frena. Una orden vale `vigencia_ms` (tope TOPE_VIGENCIA_MS) desde que llega;
//    al vencer, los motores se apagan solos y se avisa VENCIDA al último emisor.
//  - Sin WiFi, los motores se apagan.
//  - Una tarea propia revisa todo cada PERIODO_REVISION_MS, aparte del servidor de video.
//  - Nunca hay reversa: los pines "atrás" se quedan en bajo.

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#include "config_carro.h"
#include "ordenes.h"

namespace {

enum Accion { AVANZAR, GIRAR_IZQ, GIRAR_DER, STOP };
const char* const ACCIONES[] = {"AVANZAR", "GIRAR_IZQ", "GIRAR_DER", "STOP"};

enum Motivo { OK, MAL_FORMADA, FUERA_RANGO, INCONSISTENTE, SESION, SEQ_VIEJA, VENCIDA };
const char* const MOTIVOS[] = {"OK",     "MAL_FORMADA", "FUERA_RANGO", "INCONSISTENTE",
                               "SESION", "SEQ_VIEJA",   "VENCIDA"};

const uint64_t MAX_U32 = 4294967295ULL;

struct Orden {
  uint64_t sesion = 0;
  uint64_t seq = 0;
  int accion = STOP;
  float velocidad = 0;
  float giro = 0;
  uint64_t vigencia_ms = 0;
};

struct Lado {
  int pinPwm;   // el pin "adelante" de ese lado (después de las correcciones)
  int pinBajo;  // el pin "atrás": siempre en bajo
  int canal;
};

WiFiUDP udp;
Lado izq, der;

// Estado de la placa (solo lo toca la tarea de órdenes).
uint64_t sesionActiva = 0;  // 0 = ninguna (recién encendida): cualquier STOP abre sesión
uint64_t ultimaSeq = 0;
bool hayVencimiento = false;
uint32_t venceMs = 0;
int pwmIzq = 0, pwmDer = 0;
IPAddress emisorIp;
uint16_t emisorPuerto = 0;
bool hayEmisor = false;
int ultimaAccionImpresa = -1;

// --- Motores ---------------------------------------------------------------------------

void armarLados() {
  int ia = PIN_IZQ_ADELANTE, ib = PIN_IZQ_ATRAS, da = PIN_DER_ADELANTE, db = PIN_DER_ATRAS;
#if INVERTIR_IZQ
  int t = ia; ia = ib; ib = t;
#endif
#if INVERTIR_DER
  int u = da; da = db; db = u;
#endif
#if INTERCAMBIAR_LADOS
  izq = {da, db, CANAL_IZQ};
  der = {ia, ib, CANAL_DER};
#else
  izq = {ia, ib, CANAL_IZQ};
  der = {da, db, CANAL_DER};
#endif
}

void aplicarPwm(int i, int d) {
  pwmIzq = constrain(i, 0, 255);
  pwmDer = constrain(d, 0, 255);
  ledcWrite(izq.canal, pwmIzq);
  ledcWrite(der.canal, pwmDer);
}

void frenar() {
  aplicarPwm(0, 0);
  hayVencimiento = false;
}

bool moviendo() { return pwmIzq != 0 || pwmDer != 0; }

int aPwm(float fraccion) {
  if (fraccion <= 0) return 0;
  if (fraccion > 1) fraccion = 1;
  return lroundf(MINIMO_PWM + fraccion * (TECHO_PWM - MINIMO_PWM));
}

// --- Lectura de la orden -----------------------------------------------------------------

bool entero(const char* s, int maxDigitos, uint64_t& v) {
  int n = 0;
  v = 0;
  for (; s[n]; ++n) {
    if (s[n] < '0' || s[n] > '9' || n >= maxDigitos) return false;
    v = v * 10 + (s[n] - '0');
  }
  return n > 0;
}

// -?d(.d{1,3})?  (igual que la expresión de protocolo.py)
bool decimal(const char* s, float& v) {
  const char* p = s;
  bool negativo = false;
  if (*p == '-') {
    negativo = true;
    ++p;
  }
  if (*p < '0' || *p > '9') return false;
  long entera = *p - '0';
  ++p;
  long frac = 0;
  int digitos = 0;
  if (*p == '.') {
    ++p;
    while (*p >= '0' && *p <= '9') {
      if (digitos == 3) return false;
      frac = frac * 10 + (*p - '0');
      ++digitos;
      ++p;
    }
    if (digitos == 0) return false;
  }
  if (*p) return false;
  static const float divisor[] = {1, 10, 100, 1000};
  v = entera + frac / divisor[digitos];
  if (negativo) v = -v;
  return true;
}

// Reglas 1 a 3. `conIds` dice si sesión y seq se pudieron leer (para la respuesta).
Motivo leerOrden(char* texto, int largo, Orden& o, bool& conIds) {
  conIds = false;
  if (largo > MAX_BYTES_ORDEN || (int)strlen(texto) != largo) return MAL_FORMADA;
  if (largo > 0 && texto[largo - 1] == '\n') texto[--largo] = 0;
  for (int i = 0; i < largo; ++i) {
    if (texto[i] < 32 || texto[i] > 126) return MAL_FORMADA;
  }
  char* campos[7];
  int n = 0;
  campos[n++] = texto;
  for (char* p = texto; *p; ++p) {
    if (*p == ',') {
      if (n == 7) return MAL_FORMADA;
      *p = 0;
      campos[n++] = p + 1;
    }
  }
  if (n != 7 || strcmp(campos[0], "P5C1") != 0) return MAL_FORMADA;
  int accion = -1;
  for (int a = 0; a < 4; ++a) {
    if (strcmp(campos[3], ACCIONES[a]) == 0) accion = a;
  }
  if (accion < 0 || !entero(campos[1], 10, o.sesion) || !entero(campos[2], 10, o.seq) ||
      !decimal(campos[4], o.velocidad) || !decimal(campos[5], o.giro) ||
      !entero(campos[6], 5, o.vigencia_ms)) {
    return MAL_FORMADA;
  }
  o.accion = accion;
  conIds = true;

  if (o.sesion < 1 || o.sesion > MAX_U32 || o.seq < 1 || o.seq > MAX_U32 ||
      o.velocidad < 0 || o.velocidad > 1 || o.giro < -1 || o.giro > 1 ||
      o.vigencia_ms < 1 || o.vigencia_ms > TOPE_VIGENCIA_MS) {
    return FUERA_RANGO;
  }
  const float v = o.velocidad, g = o.giro;
  bool coherente;
  switch (o.accion) {
    case STOP: coherente = v == 0 && g == 0; break;
    case AVANZAR: coherente = v > 0 && g == 0; break;
    case GIRAR_IZQ: coherente = v > 0 && g < 0; break;
    default: coherente = v > 0 && g > 0; break;  // GIRAR_DER
  }
  return coherente ? OK : INCONSISTENTE;
}

// --- Respuestas ------------------------------------------------------------------------

void responder(IPAddress ip, uint16_t puerto, uint64_t sesion, uint64_t seq, Motivo m) {
  char r[96];
  int n = snprintf(r, sizeof(r), "P5R1,%llu,%llu,%s,%s,%d,%d,%lu", (unsigned long long)sesion,
                   (unsigned long long)seq, MOTIVOS[m], moviendo() ? "MOVIENDO" : "DETENIDO",
                   pwmIzq, pwmDer, (unsigned long)millis());
  udp.beginPacket(ip, puerto);
  udp.write((const uint8_t*)r, n);
  udp.endPacket();
}

// --- Reglas 4 y 5 y aplicación (igual que Placa.recibir) ----------------------------------

void procesar(char* texto, int largo, IPAddress ip, uint16_t puerto) {
  Orden o;
  bool conIds;
  Motivo m = leerOrden(texto, largo, o, conIds);
  if (m == OK) {
    if (o.sesion != sesionActiva) {
      // Las sesiones solo crecen: un STOP atrasado de una sesión anterior no la revive.
      if (o.accion != STOP || o.sesion < sesionActiva) {
        m = SESION;
      } else {
        sesionActiva = o.sesion;
        ultimaSeq = 0;
      }
    }
    if (m == OK && o.seq <= ultimaSeq) m = SEQ_VIEJA;
  }

  if (m != OK) {
    frenar();
    Serial.printf("rechazo %s -> STOP\n", MOTIVOS[m]);
    ultimaAccionImpresa = -1;
    responder(ip, puerto, conIds ? o.sesion : 0, conIds ? o.seq : 0, m);
    return;
  }

  ultimaSeq = o.seq;
  emisorIp = ip;
  emisorPuerto = puerto;
  hayEmisor = true;
  if (o.accion == STOP) {
    frenar();
  } else {
    float fi = o.velocidad, fd = o.velocidad;  // giro < 0 = izquierda: frena el lado izquierdo
    if (o.giro < 0) fi = o.velocidad * (1 + o.giro);
    if (o.giro > 0) fd = o.velocidad * (1 - o.giro);
    aplicarPwm(aPwm(fi), aPwm(fd));
    venceMs = millis() + (uint32_t)o.vigencia_ms;
    hayVencimiento = true;
  }
  if (o.accion != ultimaAccionImpresa) {  // una línea por cambio, no 10 por segundo
    Serial.printf("orden %s pwm=%d/%d\n", ACCIONES[o.accion], pwmIzq, pwmDer);
    ultimaAccionImpresa = o.accion;
  }
  responder(ip, puerto, o.sesion, o.seq, OK);
}

void tareaOrdenes(void*) {
  char buf[MAX_BYTES_ORDEN + 2];
  for (;;) {
    if (WiFi.status() != WL_CONNECTED && moviendo()) {
      frenar();
      Serial.println("WiFi perdido -> STOP");
      ultimaAccionImpresa = -1;
    }
    int tam;
    while ((tam = udp.parsePacket()) > 0) {
      int leidos = udp.read((uint8_t*)buf, sizeof(buf) - 1);
      buf[leidos < 0 ? 0 : leidos] = 0;
      // Un datagrama más largo que el búfer se trata como mal formado (tam > MAX_BYTES).
      procesar(buf, tam, udp.remoteIP(), udp.remotePort());
    }
    if (hayVencimiento && (int32_t)(millis() - venceMs) >= 0) {
      frenar();
      Serial.println("orden vencida -> STOP");
      ultimaAccionImpresa = -1;
      if (hayEmisor) responder(emisorIp, emisorPuerto, sesionActiva, ultimaSeq, VENCIDA);
    }
    vTaskDelay(pdMS_TO_TICKS(PERIODO_REVISION_MS));
  }
}

}  // namespace

void motoresSeguros() {
  const int pines[] = {PIN_IZQ_ADELANTE, PIN_IZQ_ATRAS, PIN_DER_ADELANTE, PIN_DER_ATRAS,
                       PIN_LED_FLASH};
  for (int p : pines) {
    pinMode(p, OUTPUT);
    digitalWrite(p, LOW);
  }
}

void iniciarOrdenes() {
  armarLados();
  ledcSetup(izq.canal, PWM_HZ, PWM_BITS);
  ledcSetup(der.canal, PWM_HZ, PWM_BITS);
  ledcAttachPin(izq.pinPwm, izq.canal);
  ledcAttachPin(der.pinPwm, der.canal);
  digitalWrite(izq.pinBajo, LOW);
  digitalWrite(der.pinBajo, LOW);
  frenar();
  udp.begin(PUERTO_ORDENES);
  // Prioridad arriba del servidor HTTP (5) para que el stream no atrase los paros.
  xTaskCreatePinnedToCore(tareaOrdenes, "ordenes", 4096, nullptr, 6, nullptr, 1);
  Serial.printf("Ordenes UDP en el puerto %d (techo=%d, minimo=%d, tope=%d ms)\n",
                PUERTO_ORDENES, TECHO_PWM, MINIMO_PWM, TOPE_VIGENCIA_MS);
}
