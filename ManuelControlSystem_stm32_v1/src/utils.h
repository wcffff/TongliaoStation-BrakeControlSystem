#pragma once
#include <Arduino.h>
#include <HardwareSerial.h>
#include <SoftwareSerial.h>
#include <STM32FreeRTOS.h>
#include <cstdint> 

// # define SERIAL_DEBUG

#ifdef SERIAL_DEBUG
    const uint8_t DEBUG_SERIAL_RX_PIN = PA10;
    const uint8_t DEBUG_SERIAL_TX_PIN = PA9;
#endif

// Define State of the Device
enum STATE {
  STATE_INIT = 1,
  STATE_STOP_AT_BRAKE_OKAY,
  STATE_STOP_AT_RELEASE_OKAY,
  STATE_STOP_AT_MIDDLE,
  STATE_BRAKING,
  STATE_RELEASING,
  WARNING_NOT_IN_PLACE = 10,
  ERROR_BOTH_SWITCH_ON = 100,
  ERROR_RELEASE_SWITCH_ON,
  ERROR_BRAKE_SWITCH_OFF,
  ERROR_BRAKE_SWITCH_ON,
  ERROR_RELEASE_SWITCH_OFF,
  ERROR_BRAKE_TIMEOUT = 110,
  ERROR_RELEASE_TIMEOUT
};

// Define State Variables for Msg Receiving
enum RxState {
  RX_HEADER,
  RX_TYPE,
  RX_TRACK,
  RX_DEVICE,
  RX_STATE,
  RX_IO,
  RX_TAIL,
  RX_CHECKSUM
};

// Define STM32 Pins
const uint8_t BrakeButtonPin[] = {PC7, PC11, PA15, PD4, PG9, PG13, PB4, PE2, PF3};
const uint8_t ReleaseButtonPin[] = {PG4, PC6, PA8, PD1, PD3, PD7, PG12, PE6, PF0};

const uint8_t BrakeLEDPin[] = {PD13, PF7, PD11, PB10, PE12, PF15, PC5, PA3, PA0};
const uint8_t ReleaseLEDPin[] = {PG6, PF8, PB15, PE15, PE9, PG0, PF12, PA6, PA12};
const uint8_t ErrorLEDPin[] = {PD12, PD10, PB12, PE13, PE8, PF11, PB0, PA1, PA11};

const uint8_t SERIAL_RX_1 = PD14;
const uint8_t SERIAL_TX_1 = PD15;

const uint8_t SERIAL_RX_2 = PB5;
const uint8_t SERIAL_TX_2 = PB6;

const uint8_t SERIAL_RX_3 = PE0;
const uint8_t SERIAL_TX_3 = PE1;

const uint8_t CentralControlPin = PG5;

// Define Message Format
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

class Button {
    private:
        uint8_t pin;
        bool lastState;
        uint32_t lastDebounceTime;
        uint32_t debounceDelay;
        bool stableState;
    
    public:
        Button(uint8_t buttonPin, uint32_t delay = 10) 
            : pin(buttonPin), lastState(LOW), 
              lastDebounceTime(0), debounceDelay(delay),
              stableState(LOW) {}
    
        bool read() {
            bool currentState = digitalRead(pin);
            if (currentState != lastState) {
                lastDebounceTime = millis();
            }
    
            if ((millis() - lastDebounceTime) > debounceDelay) {
                if (currentState != stableState) {
                    stableState = currentState;
                }
            }
            
            lastState = currentState;
            return stableState;
        }
    };

class TrackLED{
  private:
     uint8_t brakeLEDPin;
     uint8_t releaseLEDPin;
     uint8_t errorLEDPin;
     uint32_t lastBlinkTime;
     bool blinkState;

     enum class ActiveLED{
       NONE, 
       BRAKE,
       RELEASE,
       ERROR
     };

     ActiveLED currentLED;
     bool isBlinking;

  public:
      TrackLED(uint8_t brake, uint8_t release, uint8_t error) 
          : brakeLEDPin(brake), releaseLEDPin(release), errorLEDPin(error),
          lastBlinkTime(0), blinkState(false), currentLED(ActiveLED::NONE),
          isBlinking(false) {
              turnOffAll();
          }       
      
      void turnOffAll() {
          pinMode(brakeLEDPin, INPUT_PULLUP);
          pinMode(releaseLEDPin, INPUT_PULLUP);
          pinMode(errorLEDPin, INPUT_PULLUP);
          isBlinking = false;
          currentLED = ActiveLED::NONE;
      }

      void setError(){
          turnOffAll();
          pinMode(errorLEDPin, OUTPUT);
          digitalWrite(errorLEDPin, LOW);
          currentLED = ActiveLED::ERROR;
      }

      void setBrakeOn(){
          turnOffAll();
          pinMode(brakeLEDPin, OUTPUT);
          digitalWrite(brakeLEDPin, LOW);
          currentLED = ActiveLED::BRAKE;
      }

      void setReleaseOn(){
          turnOffAll();
          pinMode(releaseLEDPin, OUTPUT);
          digitalWrite(releaseLEDPin, LOW);
          currentLED = ActiveLED::RELEASE;
      }
};

void SendControlMsg1(uint8_t trackID, uint8_t deviceID, uint8_t command);
void SendControlMsg2(uint8_t trackID, uint8_t deviceID, uint8_t command);
void SendControlMsg3(uint8_t trackID, uint8_t deviceID, uint8_t command);

bool parseByte1(unsigned char byte);
bool parseByte2(unsigned char byte);
bool parseByte3(unsigned char byte);

void updateTrackLED1(uint8_t trackID);
void updateTrackLED2(uint8_t trackID);

void updateTrackLED3(uint8_t trackID);
// void taskDetectButton(void *pvParameters);
// void taskRequest(void *pvParameters);
void taskSerial1(void *pvParameters);
void taskSerial2(void *pvParameters);
void taskSerial3(void *pvParameters);
//void taskButton(void *pvParameters);
// void taskMsgForTrack_1_3(void *pvParameters);
// void taskMsgForTrack_4_6(void *pvParameters);
// void taskMsgForTrack_7_9(void *pvParameters);
//void taskLED(void *pvParameters);

void GPIO_Init(void);

void Serial_Init(void);
void Task_Init(void);
void systemInit(void);