// P5-20: órdenes PC -> carro por UDP (protocolo v1, docs/carro/protocolo.md).
#pragma once

// Pone los pines de motor en bajo. Va en la primera línea de setup(), antes que todo.
void motoresSeguros();

// Configura el PWM y arranca la tarea de órdenes. Llamar con el WiFi ya conectado.
void iniciarOrdenes();
