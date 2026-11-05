// P5-20: parámetros del firmware del carro. Ver docs/carro/protocolo.md.
// Los valores medidos en la fase 2 se anotan en la tabla de parámetros de ese documento.
#pragma once

// --- Protocolo -------------------------------------------------------------------------
#define PUERTO_ORDENES 4210      // UDP; el 80 y el 81 siguen siendo de la cámara
#define TOPE_VIGENCIA_MS 500     // una orden nunca vale más que esto
#define MAX_BYTES_ORDEN 96
#define PERIODO_REVISION_MS 5    // cada cuánto se revisan vencimientos, WiFi y datagramas

// --- Motores ---------------------------------------------------------------------------
#define TECHO_PWM 160            // PWM máximo (0 a 255) con velocidad = 1
#define MINIMO_PWM 90            // zona muerta: el PWM más bajo que mueve las ruedas
#define PWM_HZ 1000
#define PWM_BITS 8

// Pines del L298N según el firmware del kit (IN1 a IN4).
#define PIN_IZQ_ADELANTE 14
#define PIN_IZQ_ATRAS 2          // pin de arranque: siempre en bajo
#define PIN_DER_ADELANTE 13
#define PIN_DER_ATRAS 15         // pin de arranque: siempre en bajo
#define PIN_LED_FLASH 4

// Canales LEDC del grupo de baja velocidad (8 a 15). La cámara usa el canal 0 y el timer 0
// del grupo de alta velocidad para XCLK: no se tocan.
#define CANAL_IZQ 8
#define CANAL_DER 10             // otro par: timer distinto al del lado izquierdo

// Correcciones de cableado sin recablear (fase 2, ruedas en el aire):
//  - INVERTIR_IZQ / INVERTIR_DER: ese lado gira al revés con AVANZAR.
//  - INTERCAMBIAR_LADOS: GIRAR_IZQ frena el lado derecho en vez del izquierdo.
#define INVERTIR_IZQ 0
#define INVERTIR_DER 0
#define INTERCAMBIAR_LADOS 0
