#pragma once

#include <stdint.h>
#include <Arduino.h>
#include <STM32FreeRTOS.h>
#include <HardwareSerial.h>

#define SERIAL_DEBUG

// Pin Definitions
const uint8_t FUNCTION_SELECT_PIN = PA3;

const uint8_t DEVICE_ID_PIN[] = {PE11, PE9};  // DEVICE_ID0 - DEVICE_ID1

const uint8_t TRACK_ID_PIN[] = {PG1, PF15, PF13, PF11, PB1, PC5, PA7};  // TRACK_ID0 - TRACK_ID6

const uint8_t RELEASE_ENABLE_PIN = PF8;
const uint8_t BRAKE_ENABLE_PIN = PF9;

const uint8_t SWITCH_STATUS_PIN = PE10;
const uint8_t BRAKE_STATUS_PIN = PB2;
const uint8_t RELEASE_STATUS_PIN = PA6;

const uint8_t CONTROL_BUTTON_PIN = PD6;
const uint8_t RELEASE_BUTTON_PIN = PD2;
const uint8_t BRAKE_BUTTON_PIN = PD4;

const uint8_t SERIAL_RX_PIN = PB15;
const uint8_t SERIAL_TX_PIN = PB14;

#ifdef SERIAL_DEBUG
const uint8_t DEBUG_SERIAL_RX_PIN = PA10;
const uint8_t DEBUG_SERIAL_TX_PIN = PA9;
#endif

const uint8_t LED_R_PIN = PG0;
const uint8_t LED_G_PIN = PF14;
const uint8_t LED_B_PIN = PF12;

const uint8_t IO_PIN_LOW[] = {PE4, PE2, PB9, PE1, PB6, PB4, PG15, PG13};  // IO1 - IO8

const uint8_t IO_PIN_HIGH[] = {PG11};  // IO9 - IO16

// Variable Definitions
enum FunctionSelect {
    FUNCTION_ANTI_SLIDE = LOW,
    FUNCTION_BRAKE = HIGH,
};
enum CONTROL_STATUS {
    CONTROL_LOCAL = HIGH,
    CONTROL_REMOTE = LOW
};

enum BUTTON_STATUS {
    BUTTON_PRESSED = HIGH,
    BUTTON_NOT_PRESSED = LOW
};

enum SWITCH_STATUS {
    SWITCH_IN_PLACE = HIGH,
    SWITCH_NOT_IN_PLACE = LOW
};

enum COMMAND_STATUS {
    COMMAND_ENABLE = LOW,
    COMMAND_DISABLE = HIGH,
};

enum REMOTE_COMMAND {
    COMMAND_BRAKE,
    COMMAND_RELEASE,
    COMMAND_REQUEST,
    COMMAND_NULL
};

enum STATE {
    STATE_INIT = 1,
    STATE_STOP_AT_BRAKE_REMOTE = 2,
    STATE_STOP_AT_RELEASE_REMOTE = 3,
    STATE_STOP_LOCAL = 4,
    STATE_BRAKING_REMOTE = 5,
    STATE_RELEASING_REMOTE = 6,
    STATE_BRAKING_LOCAL = 7,
    STATE_RELEASING_LOCAL = 8,
    STATE_PUSH_AWAY = 9,
    WARNING_NOT_IN_PLACE = 10,
    ERROR_BOTH_SWITCH_ON = 100,
    ERROR_RELEASE_SWITCH_ON,
    ERROR_BRAKE_SWITCH_OFF,
    ERROR_BRAKE_SWITCH_ON,
    ERROR_RELEASE_SWITCH_OFF,
    ERROR_BRAKE_TIMEOUT = 110,
    ERROR_RELEASE_TIMEOUT,
	ERROR_NOT_UNIFIED_RELEASE = 120,
	ERROR_NOT_UNIFIED_BRAKE
};

const uint64_t serialTimeout = 5000;
const uint64_t operationTimeoutBrake = 22000;
const uint64_t operationTimeoutAntiSlide = 22000;
const uint64_t detectionInterval = 5000;

const uint8_t debounce_threshold = 5;

const uint8_t PACKET_HEADER = 0xAA;
const uint8_t PACKET_TAIL = 0x55;

const uint8_t PACKET_UPSTREAM = 0x01;
const uint8_t PACKET_DOWNSTREAM = 0x02;

const uint8_t PACKET_FUNCTION_BRAKE = 0x01;
const uint8_t PACKET_FUNCTION_ANTI_SLIDE = 0x02;

const uint8_t PACKET_CONTROL_LOCAL = 0x01;
const uint8_t PACKET_CONTROL_REMOTE = 0x02;

const uint8_t PACKET_COMMAND_REQUEST = 0x01;
const uint8_t PACKET_COMMAND_BRAKE = 0x02;
const uint8_t PACKET_COMMAND_RELEASE = 0x03;
const uint8_t PACKET_COMMAND_NULL = 0x04;

// Function Declarations
#ifdef SERIAL_DEBUG

void debugSerialInit();

#endif

void serialInit();

void gpioInit();

void peripheralInit();

[[noreturn]] void taskInit();

void systemInit();

[[noreturn]] void taskUpdateCommand(void *pvParameters);

[[noreturn]] void taskUpdateSate(void *pvParameters);

void brakeOn();

void brakeOff();

void releaseOn();

void releaseOff();

void ledOn(uint8_t r = LOW, uint8_t g = LOW, uint8_t b = LOW);

void ledOff();

void ledUpdate(uint8_t error);

void readFunction();

void readID();

uint8_t readReleaseStatus();

uint8_t readBrakeStatus();

uint8_t readSwitchStatus();

uint8_t readControlButton();

uint8_t readBrakeButton();

uint8_t readReleaseButton();

uint8_t readIOStateHigh();

uint8_t readIOStateLow();

bool parseByte(uint8_t byte, volatile uint8_t &command);
