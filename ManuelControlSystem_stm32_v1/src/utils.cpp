# include "utils.h"

volatile uint8_t track_1_3_Status[3][3] = {0}; // 1-3 roads, 3 devices each
volatile uint8_t track_4_6_Status[3][3] = {0}; // 4-6 roads, 3 devices each
volatile uint8_t track_7_9_Status[3][3] = {0}; // 7-9 roads, 3 devices each

volatile unsigned long long commu_time1[3][3] = {0};
volatile unsigned long long commu_time2[3][3] = {0};
volatile unsigned long long commu_time3[3][3] = {0};

volatile bool commu_error1[3] = {true, true, true};
volatile bool commu_error2[3] = {true, true, true};
volatile bool commu_error3[3] = {true, true, true};

volatile SemaphoreHandle_t xState1Semaphore = xSemaphoreCreateMutex();
volatile SemaphoreHandle_t xState2Semaphore = xSemaphoreCreateMutex();
volatile SemaphoreHandle_t xState3Semaphore = xSemaphoreCreateMutex();

volatile SemaphoreHandle_t xTime1Semaphore = xSemaphoreCreateMutex();
volatile SemaphoreHandle_t xTime2Semaphore = xSemaphoreCreateMutex();
volatile SemaphoreHandle_t xTime3Semaphore = xSemaphoreCreateMutex();

// 按钮0状态表示未被按下
volatile uint8_t buttonState[9][2] = {0};
volatile uint8_t buttonTrackID = 0;
volatile uint8_t buttonCommandID = 0;
volatile SemaphoreHandle_t xButtonSemaphore = xSemaphoreCreateMutex();

HardwareSerial hwSerial1(SERIAL_RX_1, SERIAL_TX_1);
SoftwareSerial hwSerial2(SERIAL_RX_2, SERIAL_TX_2);
HardwareSerial hwSerial3(SERIAL_RX_3, SERIAL_TX_3);

TrackLED trackLED[9] = {
    TrackLED(BrakeLEDPin[0], ReleaseLEDPin[0], ErrorLEDPin[0]),
    TrackLED(BrakeLEDPin[1], ReleaseLEDPin[1], ErrorLEDPin[1]),
    TrackLED(BrakeLEDPin[2], ReleaseLEDPin[2], ErrorLEDPin[2]),
    TrackLED(BrakeLEDPin[3], ReleaseLEDPin[3], ErrorLEDPin[3]),
    TrackLED(BrakeLEDPin[4], ReleaseLEDPin[4], ErrorLEDPin[4]),
    TrackLED(BrakeLEDPin[5], ReleaseLEDPin[5], ErrorLEDPin[5]),
    TrackLED(BrakeLEDPin[6], ReleaseLEDPin[6], ErrorLEDPin[6]),
    TrackLED(BrakeLEDPin[7], ReleaseLEDPin[7], ErrorLEDPin[7]),
    TrackLED(BrakeLEDPin[8], ReleaseLEDPin[8], ErrorLEDPin[8])
  };

void GPIO_Init(void){

    // Initialize GPIO pins for buttons and LEDs
    for (uint8_t pin : BrakeButtonPin) {
      pinMode(pin, INPUT_PULLUP);
    }
    for (uint8_t pin : ReleaseButtonPin) {
      pinMode(pin, INPUT_PULLUP);
    }
    for (uint8_t pin : BrakeLEDPin) {
      pinMode(pin, OUTPUT);
    }
    for (uint8_t pin : ReleaseLEDPin) {
      pinMode(pin, OUTPUT);
    }
    for (uint8_t pin : ErrorLEDPin) {
      pinMode(pin, OUTPUT);
    }
    pinMode(CentralControlPin, INPUT_PULLUP);
  }
  
void Serial_Init(void){
  // Initialize Serial communication  
  hwSerial1.begin(115200);
  hwSerial2.begin(115200);
  hwSerial3.begin(115200);

  #ifdef SERIAL_DEBUG
    HardwareSerial debugSerial(DEBUG_SERIAL_RX_PIN, DEBUG_SERIAL_TX_PIN);
    debugSerial.begin(115200);
    debugSerial.println("Debug Serial Initialization Finished!");
  #endif

}

void Task_Init(void){
  // Initialize FreeRTOS tasks
  if (xState1Semaphore == nullptr) {
    xState1Semaphore = xSemaphoreCreateMutex();
    if ((xState1Semaphore) != nullptr) {
        xSemaphoreGive(xState1Semaphore);
    }
  }
  if (xState2Semaphore == nullptr) {
    xState2Semaphore = xSemaphoreCreateMutex();
    if ((xState2Semaphore) != nullptr) {
        xSemaphoreGive(xState2Semaphore);
    }
  }
  if (xState3Semaphore == nullptr) {
    xState3Semaphore = xSemaphoreCreateMutex();
    if ((xState3Semaphore) != nullptr) {
        xSemaphoreGive(xState3Semaphore);
    }
  }

  if (xTime1Semaphore == nullptr) {
    xTime1Semaphore = xSemaphoreCreateMutex();
    if ((xTime1Semaphore) != nullptr) {
        xSemaphoreGive(xTime1Semaphore);
    }
  }
  if (xTime2Semaphore == nullptr) {
    xTime2Semaphore = xSemaphoreCreateMutex();
    if ((xTime2Semaphore) != nullptr) {
        xSemaphoreGive(xTime2Semaphore);
    }
  }
  if (xTime3Semaphore == nullptr) {
    xTime3Semaphore = xSemaphoreCreateMutex();
    if ((xTime3Semaphore) != nullptr) {
        xSemaphoreGive(xTime3Semaphore);
    }
  }

  //xTaskCreate(taskLED, "LED", configMINIMAL_STACK_SIZE * 20, nullptr, 1, nullptr);

  xTaskCreate(taskSerial3, "serial3", configMINIMAL_STACK_SIZE * 10, nullptr, 1, nullptr);
  xTaskCreate(taskSerial2, "serial2", configMINIMAL_STACK_SIZE * 10, nullptr, 2, nullptr);
  xTaskCreate(taskSerial1, "serial1", configMINIMAL_STACK_SIZE * 10, nullptr, 3, nullptr);

  //xTaskCreate(taskButton, "Button", configMINIMAL_STACK_SIZE * 100, nullptr, 4, nullptr);
  vTaskStartScheduler();
}

void systemInit(void) {
  // Initialize system components
  GPIO_Init();
  Serial_Init();
  Task_Init();
}

void SendControlMsg1(uint8_t trackID, uint8_t deviceID, uint8_t command) {
  // Function to send control messages to the device
  uint8_t packet[8] = {
    PACKET_HEADER,
    0x8A,
    trackID,
    deviceID,
    command,
    0x00,  
    PACKET_TAIL,
    0x00   // Placeholder for checksum
  };
  
  // Calculate checksum
  for (uint8_t i = 0; i < 7; i++) {
    packet[7] ^= packet[i];
  }
  
  // Send packet via serial
  hwSerial1.write(packet, sizeof(packet));
}

void SendControlMsg2(uint8_t trackID, uint8_t deviceID, uint8_t command) {
  // Function to send control messages to the device
  uint8_t packet[8] = {
    PACKET_HEADER,
    0x8A,
    trackID,
    deviceID,
    command,
    0x00,  
    PACKET_TAIL,
    0x00   // Placeholder for checksum
  };
  
  // Calculate checksum
  for (uint8_t i = 0; i < 7; i++) {
    packet[7] ^= packet[i];
  }
  
  // Send packet via serial
  hwSerial2.write(packet, sizeof(packet));
}

void SendControlMsg3(uint8_t trackID, uint8_t deviceID, uint8_t command) {
  // Function to send control messages to the device
  uint8_t packet[8] = {
    PACKET_HEADER,
    0x8A,
    trackID,
    deviceID,
    command,
    0x00,  
    PACKET_TAIL,
    0x00   // Placeholder for checksum
  };
  
  // Calculate checksum
  for (uint8_t i = 0; i < 7; i++) {
    packet[7] ^= packet[i];
  }
  
  // Send packet via serial
  hwSerial3.write(packet, sizeof(packet));
}

bool parseByte1(unsigned char byte)
{
    static unsigned char checksum = 0;
    static unsigned char step = 0;
    static uint8_t track = 0;
    static uint8_t device = 0;
    static uint8_t state = 0;

    switch (step){
        case 0:
            if (byte == PACKET_HEADER) {
                checksum = PACKET_HEADER;
                step++;
            }
            break;

        case 1:
            if (byte == 0x4A || byte == 0x49) {
                checksum ^= byte;
                step++;
            } else {
                step = 0;
            }
            break;
        
        case 2:
            if (byte >= 1 && byte <= 3) {
                track = byte;
                checksum ^= byte;
                step++;
            } else {
                step = 0;
            }
            break;

        case 3:
            if (byte >= 1 && byte <= 3) {
                device = byte;
                checksum ^= byte;
                step++;
            } else {
                step = 0;
            }
            break;

        case 4:
            if ((byte >= STATE_INIT && byte <= STATE_RELEASING) ||
                (byte == WARNING_NOT_IN_PLACE) ||
                (byte >= ERROR_BOTH_SWITCH_ON && byte <= ERROR_RELEASE_TIMEOUT)) {           
                state = byte;
                checksum ^= byte;
                step++;
            } else {
                step = 0;  
            }
            break;
        
        case 5:
            checksum ^= byte;
            step++;
            break;

        case 6:
            if (byte == PACKET_TAIL) {
                checksum ^= byte; // Update checksum with tail
                step++;
            } else {
                step = 0;  
            }
            break;

        case 7:
            step = 0;
            if (byte == checksum) {
                if (xSemaphoreTake(xState1Semaphore, 5) == pdTRUE) {
                    track_1_3_Status[track - 1][device - 1] = state;
                    xSemaphoreGive(xState1Semaphore);
                  }
                if (xSemaphoreTake(xTime1Semaphore, 5) == pdTRUE) {
                    commu_time1[track - 1][device - 1] = millis();
                    xSemaphoreGive(xTime1Semaphore);
                }
                return true;
            }
            break;
            
        default:
            step = 0;
            break;     
    }
    return false;
}

bool parseByte2(unsigned char byte)
{
    static unsigned char checksum = 0;
    static unsigned char step = 0;
    static uint8_t track = 0;
    static uint8_t device = 0;
    static uint8_t state = 0;

    switch (step){
        case 0:
            if (byte == PACKET_HEADER) {
                checksum = PACKET_HEADER;
                step++;
            }
            break;

        case 1:
            if (byte == 0x4A || byte == 0x49) {
                checksum ^= byte;
                step++;
            } else {
                step = 0;
            }
            break;
        
        case 2:
            if (byte >= 4 && byte <= 6) {
                track = byte;
                checksum ^= byte;
                step++;
            } else {
                step = 0;
            }
            break;

        case 3:
            if (byte >= 1 && byte <= 3) {
                device = byte;
                checksum ^= byte;
                step++;
            } else {
                step = 0;
            }
            break;

        case 4:
            if ((byte >= STATE_INIT && byte <= STATE_RELEASING) ||
                (byte == WARNING_NOT_IN_PLACE) ||
                (byte >= ERROR_BOTH_SWITCH_ON && byte <= ERROR_RELEASE_TIMEOUT)) {           
                state = byte;
                checksum ^= byte;
                step++;
            } else {
                step = 0;  
            }
            break;
        
        case 5:
            checksum ^= byte;
            step++;
            break;

        case 6:
            if (byte == PACKET_TAIL) {
                checksum ^= byte; // Update checksum with tail
                step++;
            } else {
                step = 0;  
            }
            break;

        case 7:
            step = 0;
            if (byte == checksum) {
                if (xSemaphoreTake(xState2Semaphore, 5) == pdTRUE) {
                    track_4_6_Status[track - 4][device - 1] = state;
                    xSemaphoreGive(xState2Semaphore);
                  }
                if (xSemaphoreTake(xTime2Semaphore, 5) == pdTRUE) {
                    commu_time2[track - 4][device - 1] = millis();
                    xSemaphoreGive(xTime2Semaphore);
                }
                return true;
            }
            break;
            
        default:
            step = 0;
            break;
        
    }
    return false;
}

bool parseByte3(unsigned char byte)
{
    static unsigned char checksum = 0;
    static unsigned char step = 0;
    static uint8_t track = 0;
    static uint8_t device = 0;
    static uint8_t state = 0;

    switch (step){
        case 0:
            if (byte == PACKET_HEADER) {
                checksum = PACKET_HEADER;
                step++;
            }
            break;

        case 1:
            if (byte == 0x4A || byte == 0x49) {
                checksum ^= byte;
                step++;
            } else {
                step = 0;
            }
            break;
        
        case 2:
            if (byte >= 7 && byte <= 9) {
                track = byte;
                checksum ^= byte;
                step++;
            } else {
                step = 0;
            }
            break;

        case 3:
            if (byte >= 1 && byte <= 3) {
                device = byte;
                checksum ^= byte;
                step++;
            } else {
                step = 0;
            }
            break;

        case 4:
            if ((byte >= STATE_INIT && byte <= STATE_RELEASING) ||
                (byte == WARNING_NOT_IN_PLACE) ||
                (byte >= ERROR_BOTH_SWITCH_ON && byte <= ERROR_RELEASE_TIMEOUT)) {           
                state = byte;
                checksum ^= byte;
                step++;
            } else {
                step = 0;  
            }
            break;
        
        case 5:
            checksum ^= byte;
            step++;
            break;

        case 6:
            if (byte == PACKET_TAIL) {
                checksum ^= byte; // Update checksum with tail
                step++;
            } else {
                step = 0;  
            }
            break;

        case 7:
            step = 0;
            if (byte == checksum) {
                if (xSemaphoreTake(xState3Semaphore, 5) == pdTRUE) {
                    track_7_9_Status[track - 7][device - 1] = state;
                    xSemaphoreGive(xState3Semaphore);
                  }
                if (xSemaphoreTake(xTime3Semaphore, 5) == pdTRUE) {
                    commu_time3[track - 7][device - 1] = millis();
                    xSemaphoreGive(xTime3Semaphore);
                }
                return true;
            }
            break;
            
        default:
            step = 0;
            break;
        
    }
    return false;
}

void updateComErrorLED(uint8_t trackID){
    trackLED[trackID].setError();
}

void updateTrackLED1(uint8_t trackID) {
  if (xSemaphoreTake(xState1Semaphore, 5) == pdTRUE) 
  {
    bool hasError = false;
    bool allBrakeComplete = true;    // 是否全部是状态2（制动完成）
    bool allReleaseComplete = true;  // 是否全部是状态3（缓解完成）

    // 单次遍历，同时检查所有条件
    for (int i = 0; i < 3; i++) {
        uint8_t state = track_1_3_Status[trackID][i];

        // 检查故障（最高优先级）
        if (state >= 100) {
            hasError = true;
            break; // 发现故障，直接退出循环
        }

        // 检查全制动完成（状态2）
        if (state != STATE_STOP_AT_BRAKE_OKAY) {
            allBrakeComplete = false;
        }

        // 检查全缓解完成（状态3）
        if (state != STATE_STOP_AT_RELEASE_OKAY) {
            allReleaseComplete = false;
        }
    }
    xSemaphoreGive(xState1Semaphore);

    // 按优先级更新LED
    if (hasError) {
        trackLED[trackID].setError();
    } else if (allBrakeComplete) {
        trackLED[trackID].setBrakeOn();
    } else if (allReleaseComplete) {
        trackLED[trackID].setReleaseOn();
    } else {
        trackLED[trackID].turnOffAll();
    }  
  }
}

void updateTrackLED2(uint8_t trackID) {
  if (xSemaphoreTake(xState2Semaphore, 5) == pdTRUE) 
  {
    bool hasError = false;
    bool allBrakeComplete = true;    // 是否全部是状态2（制动完成）
    bool allReleaseComplete = true;  // 是否全部是状态3（缓解完成）

    // 单次遍历，同时检查所有条件
    for (int i = 0; i < 3; i++) {
        uint8_t state = track_4_6_Status[trackID-3][i];

        // 检查故障（最高优先级）
        if (state >= 100) {
            hasError = true;
            break; // 发现故障，直接退出循环
        }

        // 检查全制动完成（状态2）
        if (state != STATE_STOP_AT_BRAKE_OKAY) {
            allBrakeComplete = false;
        }

        // 检查全缓解完成（状态3）
        if (state != STATE_STOP_AT_RELEASE_OKAY) {
            allReleaseComplete = false;
        }
    }
    xSemaphoreGive(xState2Semaphore);

    // 按优先级更新LED
    if (hasError) {
        trackLED[trackID].setError();
    } else if (allBrakeComplete) {
        trackLED[trackID].setBrakeOn();
    } else if (allReleaseComplete) {
        trackLED[trackID].setReleaseOn();
    } else {
        trackLED[trackID].turnOffAll();
    }  
  }
}

void updateTrackLED3(uint8_t trackID) {
  if (xSemaphoreTake(xState3Semaphore, 5) == pdTRUE) 
  {
    bool hasError = false;
    bool allBrakeComplete = true;    // 是否全部是状态2（制动完成）
    bool allReleaseComplete = true;  // 是否全部是状态3（缓解完成）
    bool hasBraking = false;        // 是否有状态5（制动中）
    bool allBrakeValid = true;      // 是否全部是状态2或5
    bool hasReleasing = false;      // 是否有状态6（缓解中）
    bool allReleaseValid = true;    // 是否全部是状态3或6

    // 单次遍历，同时检查所有条件
    for (int i = 0; i < 3; i++) {
        uint8_t state = track_7_9_Status[trackID-6][i];

        // 检查故障（最高优先级）
        if (state >= 100) {
            hasError = true;
            break; // 发现故障，直接退出循环
        }

        // 检查全制动完成（状态2）
        if (state != STATE_STOP_AT_BRAKE_OKAY) {
            allBrakeComplete = false;
        }

        // 检查全缓解完成（状态3）
        if (state != STATE_STOP_AT_RELEASE_OKAY) {
            allReleaseComplete = false;
        }
    }
    xSemaphoreGive(xState3Semaphore);

    // 按优先级更新LED
    if (hasError) {
        trackLED[trackID].setError();
    } else if (allBrakeComplete) {
        trackLED[trackID].setBrakeOn();
    } else if (allReleaseComplete) {
        trackLED[trackID].setReleaseOn();
    } else {
        trackLED[trackID].turnOffAll();
    }  
  }
}

void taskSerial1(void *pvParameters){
  unsigned long long previousMillis = millis();
  const unsigned long long interval = 1000;
  const unsigned long long commu_interval = 5000;
  while(true)
  {   
      // 读查询回传的数据，读到后修改灯的状态并记录通讯打通的时间
      if (hwSerial1.available() && parseByte1(hwSerial1.read())){ 
      
      }
      // 判断6s内是否有通讯障碍，有则将该股道数据置0
      else{
        for (uint8_t track = 0; track<3; track++){
            for (uint8_t device = 0; device<3; device++){
                if (xSemaphoreTake(xTime1Semaphore, 5) == pdTRUE) {
                    unsigned long long current_time = millis();
                    unsigned long long last_commu_time = commu_time1[track][device];
                    if (current_time - last_commu_time > commu_interval){
                        commu_error1[track] = true;
                    }else{
                        commu_error1[track] = false;
                    }
                    xSemaphoreGive(xTime1Semaphore);
                }
            }
        }  
      }
      
      // 发送查询指令
      unsigned long long currentMillis = millis();
      if(currentMillis - previousMillis >= interval){
          SendControlMsg1(0x00, 0x00, PACKET_COMMAND_REQUEST);
          //hwSerial1.println("Request sent to serial1");
          previousMillis = currentMillis;
      }
      
      // 按钮发送指令
      bool centralControl = digitalRead(CentralControlPin);
      if (centralControl == LOW){
        for (uint8_t i = 0; i < 3; i++){
          uint8_t trackID = i + 1;
          bool brakeButtonState = digitalRead(BrakeButtonPin[i]);
          bool releaseButtonState = digitalRead(ReleaseButtonPin[i]);

          // 获取按钮状态->轨道i+1， 0表示制动，1表示缓解
          if (brakeButtonState == LOW){
            SendControlMsg1(trackID, 0x00, PACKET_COMMAND_BRAKE);
            break;
          }

          if (releaseButtonState == LOW){
            SendControlMsg1(trackID, 0x00, PACKET_COMMAND_RELEASE);
            break;
          }
        }
      }
      
      // 更新灯的状态，有通讯故障则故障灯亮，否则根据下位机状态更新灯状态
      for (uint8_t track=0; track<3; track++){
        if (commu_error1[track] == true){
            updateComErrorLED(track);
        }
        else{
            updateTrackLED1(track);
        }
      }
      
      vTaskDelay(10 / portTICK_RATE_MS);
  }
}

void taskSerial2(void *pvParameters){
  unsigned long long previousMillis = millis();
  const unsigned long long interval = 1000;
  const unsigned long long commu_interval = 5000;
  
  while(true)
  {   
    if (hwSerial2.available() && parseByte2(hwSerial2.read())){ 
        // for(int i=0; i<3; i++){
        //     for(int j=0; j<3; j++){
        //         hwSerial2.print(track_4_6_Status[i][j]);
        //         hwSerial2.print("\t");
        //     }
        //     hwSerial2.println();
        // }
    }
    else{
        for (uint8_t track = 0; track<3; track++){
            for (uint8_t device = 0; device<3; device++){
                if (xSemaphoreTake(xTime2Semaphore, 5) == pdTRUE) {
                    unsigned long long current_time = millis();
                    unsigned long long last_commu_time = commu_time2[track][device];
                    if (current_time - last_commu_time > commu_interval){
                        commu_error2[track] = true;
                    }else{
                        commu_error2[track] = false;
                    }
                    xSemaphoreGive(xTime2Semaphore);
                }
            }
    }  
    }

    unsigned long long currentMillis = millis();
    if(currentMillis - previousMillis >= interval){
        SendControlMsg2(0x00, 0x00, PACKET_COMMAND_REQUEST);
        previousMillis = currentMillis;
    }

    bool centralControl = digitalRead(CentralControlPin);
    if (centralControl == LOW){
        for (uint8_t i = 3; i < 6; i++){
            uint8_t trackID = i + 1;
            bool brakeButtonState = digitalRead(BrakeButtonPin[i]);
            bool releaseButtonState = digitalRead(ReleaseButtonPin[i]);

            // 获取按钮状态->轨道i+1， 0表示制动，1表示缓解
            if (brakeButtonState == LOW){
                SendControlMsg2(trackID, 0x00, PACKET_COMMAND_BRAKE);
                break;
            }

            if (releaseButtonState == LOW){
                SendControlMsg2(trackID, 0x00, PACKET_COMMAND_RELEASE);
                break;
            }
        }
    }

    for (uint8_t track=3; track<6; track++){
        if (commu_error2[track-3] == true){
            updateComErrorLED(track);
        }
        else{
            updateTrackLED2(track);
        }
    }

    vTaskDelay(10 / portTICK_RATE_MS);
  }
}

void taskSerial3(void *pvParameters){
  unsigned long long previousMillis = millis();
  const unsigned long long interval = 1000;
  const unsigned long long commu_interval = 5000;

  while(true)
  {   
    if (hwSerial3.available() && parseByte3(hwSerial3.read())){ 
        // for(int i=0; i<3; i++){
        //     for(int j=0; j<3; j++){
        //         hwSerial3.print(track_7_9_Status[i][j]);
        //         hwSerial3.print("\t");
        //     }
        //     hwSerial3.println();
        // }
    }
    else{
        for (uint8_t track = 0; track<3; track++){
            
            for (uint8_t device = 0; device<3; device++){
                if (xSemaphoreTake(xTime3Semaphore, 5) == pdTRUE) {
                    unsigned long long current_time = millis();
                    unsigned long long last_commu_time = commu_time3[track][device];
                    if (current_time - last_commu_time > commu_interval){
                        commu_error3[track] = true;
                    }
                    else{
                        commu_error3[track] = false;
                    }
                    xSemaphoreGive(xTime3Semaphore);
                }
            }
        }  
    }

    unsigned long long currentMillis = millis();
    if(currentMillis - previousMillis >= interval){
        SendControlMsg3(0x00, 0x00, PACKET_COMMAND_REQUEST);
        previousMillis = currentMillis;
    }

    bool centralControl = digitalRead(CentralControlPin);
    if (centralControl == LOW){
        for (uint8_t i = 6; i < 9; i++){
            uint8_t trackID = i + 1;
            bool brakeButtonState = digitalRead(BrakeButtonPin[i]);
            bool releaseButtonState = digitalRead(ReleaseButtonPin[i]);

            // 获取按钮状态->轨道i+1， 0表示制动，1表示缓解
            if (brakeButtonState == LOW){
                SendControlMsg3(trackID, 0x00, PACKET_COMMAND_BRAKE);
                break;
            }

            if (releaseButtonState == LOW){
                SendControlMsg3(trackID, 0x00, PACKET_COMMAND_RELEASE);
                break;
            }
        }
    }  

    for (uint8_t track=6; track<9; track++){
        if (commu_error3[track-6] == true){
            updateComErrorLED(track);
        }
        else{
            updateTrackLED3(track);
        }
    }

    vTaskDelay(10 / portTICK_RATE_MS);
  }
}

