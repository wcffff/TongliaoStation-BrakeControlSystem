#include "utils.h"

// Variable Definitions
volatile uint8_t function;
volatile uint8_t trackID = 0;
volatile uint8_t deviceID = 0;

volatile uint8_t releaseStatusGlobal = SWITCH_NOT_IN_PLACE;
volatile uint8_t brakeStatusGlobal = SWITCH_NOT_IN_PLACE;
volatile uint8_t switchStatusGlobal = CONTROL_LOCAL;

volatile uint8_t brakeCommandGlobal = COMMAND_DISABLE;
volatile uint8_t releaseCommandGlobal = COMMAND_DISABLE;

volatile uint8_t ioStateHighGlobal;
volatile uint8_t ioStateLowGlobal;

volatile uint8_t stateGlobal = STATE_INIT;

volatile uint8_t errorGlobal = 0x00;

volatile SemaphoreHandle_t xReleaseStatusSemaphore;
volatile SemaphoreHandle_t xBrakeStatusSemaphore;
volatile SemaphoreHandle_t xSwitchStatusSemaphore;
volatile SemaphoreHandle_t xIOStateSemaphore;


volatile SemaphoreHandle_t xBrakeCommandSemaphore;
volatile SemaphoreHandle_t xReleaseCommandSemaphore;

volatile SemaphoreHandle_t xStateSemaphore;
volatile SemaphoreHandle_t xErrorSemaphore;

HardwareSerial hwSerial(SERIAL_RX_PIN, SERIAL_TX_PIN);

#ifdef SERIAL_DEBUG
HardwareSerial debugSerial(DEBUG_SERIAL_RX_PIN, DEBUG_SERIAL_TX_PIN);
#endif

// Function Definitions
#ifdef SERIAL_DEBUG

void debugSerialInit()
{
    debugSerial.begin(115200);
    debugSerial.println("Debug Serial Initialization Finished!");
}

#endif

void serialInit()
{
    hwSerial.begin(115200);
#ifdef SERIAL_DEBUG
    debugSerial.println("Serial Initialization Finished!");
#endif
}

void gpioInit()
{
    pinMode(FUNCTION_SELECT_PIN, INPUT);

    for (const uint8_t& pin : DEVICE_ID_PIN)
    {
        pinMode(pin, INPUT);
    }

    for (const uint8_t& pin : TRACK_ID_PIN)
    {
        pinMode(pin, INPUT);
    }

    pinMode(RELEASE_ENABLE_PIN, INPUT);
    pinMode(BRAKE_ENABLE_PIN, INPUT);

    pinMode(SWITCH_STATUS_PIN, INPUT);
    pinMode(RELEASE_STATUS_PIN, INPUT);
    pinMode(BRAKE_STATUS_PIN, INPUT);

    pinMode(CONTROL_BUTTON_PIN, INPUT);
    pinMode(RELEASE_BUTTON_PIN, INPUT);
    pinMode(BRAKE_BUTTON_PIN, INPUT);

    pinMode(LED_R_PIN, OUTPUT);
    pinMode(LED_G_PIN, OUTPUT);
    pinMode(LED_B_PIN, OUTPUT);

    for (const uint8_t& pin : IO_PIN_LOW)
    {
        pinMode(pin, INPUT);
    }

    for (const uint8_t& pin : IO_PIN_HIGH)
    {
        pinMode(pin, INPUT);
    }
#ifdef SERIAL_DEBUG
    debugSerial.println("GPIO Initialization Finished!");
#endif
}

void peripheralInit()
{
    brakeOff();
    releaseOff();

    ledOn(HIGH, LOW, LOW);
    delay(333);
    ledOn(LOW, HIGH, LOW);
    delay(333);
    ledOn(LOW, LOW, HIGH);
    delay(333);
    ledOff();

    for (uint8_t i = 0; i < 50; i++)
    {
        readReleaseStatus();
        readBrakeStatus();
        readSwitchStatus();

        readControlButton();
        readReleaseButton();
        readBrakeButton();
        readIOStateHigh();
        readIOStateLow();
        delay(10);
    }

    readFunction();
    readID();

#ifdef SERIAL_DEBUG
    debugSerial.println("Peripheral Initialization Finished!");
#endif
}

[[noreturn]] void taskInit()
{
    if (xBrakeStatusSemaphore == nullptr)
    {
        xBrakeStatusSemaphore = xSemaphoreCreateMutex();
        if ((xBrakeStatusSemaphore) != nullptr)
        {
            xSemaphoreGive(xBrakeStatusSemaphore);
        }
    }
    if (xReleaseStatusSemaphore == nullptr)
    {
        xReleaseStatusSemaphore = xSemaphoreCreateMutex();
        if ((xReleaseStatusSemaphore) != nullptr)
        {
            xSemaphoreGive(xReleaseStatusSemaphore);
        }
    }
    if (xSwitchStatusSemaphore == nullptr)
    {
        xSwitchStatusSemaphore = xSemaphoreCreateMutex();
        if ((xSwitchStatusSemaphore) != nullptr)
        {
            xSemaphoreGive(xSwitchStatusSemaphore);
        }
    }
    if (xIOStateSemaphore == nullptr)
    {
        xIOStateSemaphore = xSemaphoreCreateMutex();
        if ((xIOStateSemaphore) != nullptr)
        {
            xSemaphoreGive(xIOStateSemaphore);
        }
    }
    if (xReleaseCommandSemaphore == nullptr)
    {
        xReleaseCommandSemaphore = xSemaphoreCreateMutex();
        if ((xReleaseCommandSemaphore) != nullptr)
        {
            xSemaphoreGive(xReleaseCommandSemaphore);
        }
    }
    if (xBrakeCommandSemaphore == nullptr)
    {
        xBrakeCommandSemaphore = xSemaphoreCreateMutex();
        if ((xBrakeCommandSemaphore) != nullptr)
        {
            xSemaphoreGive(xBrakeCommandSemaphore);
        }
    }
    if (xStateSemaphore == nullptr)
    {
        xStateSemaphore = xSemaphoreCreateMutex();
        if ((xStateSemaphore) != nullptr)
        {
            xSemaphoreGive(xStateSemaphore);
        }
    }
    if (xErrorSemaphore == nullptr)
    {
        xErrorSemaphore = xSemaphoreCreateMutex();
        if ((xErrorSemaphore) != nullptr)
        {
            xSemaphoreGive(xErrorSemaphore);
        }
    }

    xTaskCreate(taskUpdateCommand, (const portCHAR*)"UpdateCommand", configMINIMAL_STACK_SIZE * 50, nullptr, 2,
                nullptr);
    xTaskCreate(taskUpdateSate, (const portCHAR*)"UpdateState", configMINIMAL_STACK_SIZE * 100, nullptr, 1,
                nullptr);
#ifdef SERIAL_DEBUG
    debugSerial.println("Task Initialization Finished!");
#endif
    vTaskStartScheduler();
#ifdef SERIAL_DEBUG
    debugSerial.println("Insufficient RAM!");
#endif
    while (true)
    {
    }
}

void systemInit()
{
#ifdef SERIAL_DEBUG
    debugSerialInit();
#endif
    serialInit();
    gpioInit();
    peripheralInit();
    taskInit();
}

[[noreturn]] void taskUpdateCommand(void* pvParameters __attribute__((unused)))
{
    volatile uint8_t switchStatus = CONTROL_LOCAL;

    volatile uint8_t state = STATE_INIT;
    volatile uint8_t ioStateHigh = 0;
    volatile uint8_t ioStateLow = 0;

    volatile long long timestamp = millis();

    for (;;)
    {
        if (xSemaphoreTake(xReleaseStatusSemaphore, 5) == pdTRUE)
        {
            releaseStatusGlobal = readReleaseStatus();
            xSemaphoreGive(xReleaseStatusSemaphore);
        }
        if (xSemaphoreTake(xBrakeStatusSemaphore, 5) == pdTRUE)
        {
            brakeStatusGlobal = readBrakeStatus();
            xSemaphoreGive(xBrakeStatusSemaphore);
        }
        if (xSemaphoreTake(xSwitchStatusSemaphore, 5) == pdTRUE)
        {
            switchStatus = switchStatusGlobal = readSwitchStatus();
            xSemaphoreGive(xSwitchStatusSemaphore);
        }
        if (xSemaphoreTake(xStateSemaphore, 5) == pdTRUE)
        {
            state = stateGlobal;
            xSemaphoreGive(xStateSemaphore);
        }
        if (xSemaphoreTake(xIOStateSemaphore, 5) == pdTRUE)
        {
            ioStateHigh = ioStateHighGlobal = readIOStateHigh();
            ioStateLow = ioStateLowGlobal = readIOStateLow();
            xSemaphoreGive(xIOStateSemaphore);
        }

        volatile uint8_t remoteCommand = COMMAND_NULL;
        if (hwSerial.available() && parseByte(hwSerial.read(), remoteCommand))
        {
            timestamp = millis();
            if (xSemaphoreTake(xErrorSemaphore, 5) == pdTRUE)
            {
                errorGlobal &= 0b1101;
                ledUpdate(errorGlobal);
                xSemaphoreGive(xErrorSemaphore);
            }
        }
        else if (millis() - timestamp > serialTimeout)
        {
            if (xSemaphoreTake(xErrorSemaphore, 5) == pdTRUE)
            {
                errorGlobal |= 0b0010;
                ledUpdate(errorGlobal);
                xSemaphoreGive(xErrorSemaphore);
            }
        }

        if (remoteCommand == COMMAND_REQUEST)
        {
            uint8_t bit76 = (PACKET_UPSTREAM << 6) & 0xFF;
            uint8_t bit54 =
                ((function == FUNCTION_BRAKE ? PACKET_FUNCTION_BRAKE : PACKET_FUNCTION_ANTI_SLIDE) << 4) & 0xFF;
            uint8_t bit32 =
                ((switchStatus == CONTROL_LOCAL ? PACKET_CONTROL_LOCAL : PACKET_CONTROL_REMOTE) << 2) & 0xFF;
            uint8_t bit10 = deviceID & 0b00000011;
            uint8_t packet[] = {
                PACKET_HEADER,
                static_cast<uint8_t>((bit76 | bit54 | bit32 | bit10) & 0xFF),
                trackID,
                state,
                ioStateHigh,
                ioStateLow,
                PACKET_TAIL,
                0x00
            };
            for (uint8_t i = 0; i < 7; i++)
            {
                packet[7] ^= packet[i];
            }
            hwSerial.write(packet, sizeof(packet));
#ifdef  SERIAL_DEBUG
            debugSerial.print("Report State: ");
            for (const auto& byte : packet)
            {
                debugSerial.print(byte, HEX);
                debugSerial.print(' ');
            }
            debugSerial.println();
#endif
        }
        if (switchStatus == CONTROL_LOCAL)
        {
            if (xSemaphoreTake(xReleaseCommandSemaphore, 5) == pdTRUE)
            {
                releaseCommandGlobal = COMMAND_DISABLE;
                xSemaphoreGive(xReleaseCommandSemaphore);
            }
            if (xSemaphoreTake(xBrakeCommandSemaphore, 5) == pdTRUE)
            {
                brakeCommandGlobal = COMMAND_DISABLE;
                xSemaphoreGive(xBrakeCommandSemaphore);
            }
        }
        else
        {
            if (xSemaphoreTake(xReleaseCommandSemaphore, 5) == pdTRUE)
            {
                if (remoteCommand == COMMAND_RELEASE)
                {
                    releaseCommandGlobal = COMMAND_ENABLE;
                }
                else if (remoteCommand == COMMAND_BRAKE)
                {
                    releaseCommandGlobal = COMMAND_DISABLE;
                }
                xSemaphoreGive(xReleaseCommandSemaphore);
            }
            if (xSemaphoreTake(xBrakeCommandSemaphore, 5) == pdTRUE)
            {
                if (remoteCommand == COMMAND_BRAKE)
                {
                    brakeCommandGlobal = COMMAND_ENABLE;
                }
                else if (remoteCommand == COMMAND_RELEASE)
                {
                    brakeCommandGlobal = COMMAND_DISABLE;
                }
                xSemaphoreGive(xBrakeCommandSemaphore);
            }
        }
        vTaskDelay(5 / portTICK_RATE_MS);
    }
}

[[noreturn]] void taskUpdateSate(void* pvParameters __attribute__((unused)))
{
    volatile uint8_t state = STATE_INIT;

    volatile uint8_t releaseStatus = SWITCH_NOT_IN_PLACE;
    volatile uint8_t brakeStatus = SWITCH_NOT_IN_PLACE;
    volatile uint8_t switchStatus = CONTROL_LOCAL;

    volatile uint8_t ioStateHigh = 0;
    volatile uint8_t ioStateLow = 0;

    volatile uint8_t brakeCommand = COMMAND_DISABLE;
    volatile uint8_t releaseCommand = COMMAND_DISABLE;

    volatile long long timestamp = millis();

    volatile uint8_t unified_flag_detection_counter = 0;

    for (;;)
    {
        if (xSemaphoreTake(xStateSemaphore, 5) == pdTRUE)
        {
            stateGlobal = state;
            xSemaphoreGive(xStateSemaphore);
        }
        if (xSemaphoreTake(xReleaseStatusSemaphore, 5) == pdTRUE)
        {
            releaseStatus = releaseStatusGlobal;
            xSemaphoreGive(xReleaseStatusSemaphore);
        }
        if (xSemaphoreTake(xBrakeStatusSemaphore, 5) == pdTRUE)
        {
            brakeStatus = brakeStatusGlobal;
            xSemaphoreGive(xBrakeStatusSemaphore);
        }
        if (xSemaphoreTake(xSwitchStatusSemaphore, 5) == pdTRUE)
        {
            switchStatus = switchStatusGlobal;
            xSemaphoreGive(xSwitchStatusSemaphore);
        }
        if (xSemaphoreTake(xReleaseCommandSemaphore, 5) == pdTRUE)
        {
            releaseCommand = releaseCommandGlobal;
            xSemaphoreGive(xReleaseCommandSemaphore);
        }
        if (xSemaphoreTake(xBrakeCommandSemaphore, 5) == pdTRUE)
        {
            brakeCommand = brakeCommandGlobal;
            xSemaphoreGive(xBrakeCommandSemaphore);
        }
        if (xSemaphoreTake(xIOStateSemaphore, 5) == pdTRUE)
        {
            ioStateHigh = ioStateHighGlobal;
            ioStateLow = ioStateLowGlobal;
            xSemaphoreGive(xIOStateSemaphore);
        }

        volatile uint8_t controlButton = readControlButton();
        volatile uint8_t releaseButton = readReleaseButton();
        volatile uint8_t brakeButton = readBrakeButton();
        bool unified_flag;
        bool unified_flag_stable = true;
        uint16_t unified_flag_counter = 0;
        bool push_away;
        bool push_away_stable = false;
        uint16_t push_away_counter = 0;
        switch (state)
        {
        case STATE_INIT:
            brakeOff();
            releaseOff();
            if (brakeStatus == SWITCH_IN_PLACE && releaseStatus == SWITCH_IN_PLACE)
            {
                state = ERROR_BOTH_SWITCH_ON;
            }
            else if (brakeStatus == SWITCH_IN_PLACE && releaseStatus == SWITCH_NOT_IN_PLACE &&
                switchStatus == CONTROL_REMOTE)
            {
                push_away_stable = false;
                unified_flag_stable = true;
                push_away_counter = 0;
                unified_flag_counter = 0;
                state = STATE_STOP_AT_BRAKE_REMOTE;
            }
            else if (brakeStatus == SWITCH_IN_PLACE && releaseStatus == SWITCH_NOT_IN_PLACE &&
                switchStatus == CONTROL_LOCAL)
            {
                state = STATE_STOP_LOCAL;
            }
            else if (brakeStatus == SWITCH_NOT_IN_PLACE && releaseStatus == SWITCH_IN_PLACE &&
                switchStatus == CONTROL_REMOTE)
            {
                timestamp = millis();
                state = STATE_STOP_AT_RELEASE_REMOTE;
            }
            else if (brakeStatus == SWITCH_NOT_IN_PLACE && releaseStatus == SWITCH_IN_PLACE &&
                switchStatus == CONTROL_LOCAL)
            {
                state = STATE_STOP_LOCAL;
            }
            else if (brakeStatus == SWITCH_NOT_IN_PLACE && releaseStatus == SWITCH_NOT_IN_PLACE &&
                switchStatus == CONTROL_REMOTE)
            {
                state = WARNING_NOT_IN_PLACE;
            }
            else if (brakeStatus == SWITCH_NOT_IN_PLACE && releaseStatus == SWITCH_NOT_IN_PLACE &&
                switchStatus == CONTROL_LOCAL)
            {
                state = STATE_STOP_LOCAL;
            }
            break;
        case STATE_STOP_AT_BRAKE_REMOTE:
            brakeOff();
            releaseOff();
            unified_flag = (ioStateLow & 0b00000010) >> 1;
            push_away = (ioStateLow & 0b00000100) >> 2;

            if (push_away != push_away_stable)
            {
                push_away_counter++;
                if (push_away_counter >= 600)
                {
                    push_away_stable = push_away;
                    push_away_counter = 0;
                }
            }
            else
            {
                push_away_counter = 0;
            }

            if (unified_flag != unified_flag_stable)
            {
                unified_flag_counter++;
                if (unified_flag_counter >= 600)
                {
                    unified_flag_stable = unified_flag;
                    unified_flag_counter = 0;
                }
            }
            else
            {
                unified_flag_counter = 0;
            }

            if (releaseStatus == SWITCH_IN_PLACE)
            {
                state = ERROR_RELEASE_SWITCH_ON;
            }
            else if (brakeStatus == SWITCH_NOT_IN_PLACE)
            {
                state = ERROR_BRAKE_SWITCH_OFF;
            }
            else if (function == FUNCTION_ANTI_SLIDE && push_away_stable)
            {
                state = STATE_PUSH_AWAY;
            }
            else if (function == FUNCTION_ANTI_SLIDE && !unified_flag)
            {
                state = ERROR_NOT_UNIFIED_BRAKE;
            }
            else if (switchStatus == CONTROL_LOCAL)
            {
                state = STATE_STOP_LOCAL;
            }
            else if (releaseCommand == COMMAND_ENABLE && brakeCommand == COMMAND_DISABLE)
            {
                timestamp = millis();
                state = STATE_RELEASING_REMOTE;
            }
            break;
        case STATE_STOP_AT_RELEASE_REMOTE:
            brakeOff();
            releaseOff();
            unified_flag = ioStateLow & 0x01;
            if (brakeStatus == SWITCH_IN_PLACE)
            {
                state = ERROR_BRAKE_SWITCH_ON;
            }
            else if (releaseStatus == SWITCH_NOT_IN_PLACE)
            {
                state = ERROR_RELEASE_SWITCH_OFF;
            }
            else if (function == FUNCTION_ANTI_SLIDE && millis() - timestamp > detectionInterval && !unified_flag)
            {
                state = ERROR_NOT_UNIFIED_RELEASE;
            }
            else if (switchStatus == CONTROL_LOCAL)
            {
                state = STATE_STOP_LOCAL;
            }
            else if (releaseCommand == COMMAND_DISABLE && brakeCommand == COMMAND_ENABLE)
            {
                timestamp = millis();
                state = STATE_BRAKING_REMOTE;
            }
            break;
        case STATE_BRAKING_REMOTE:
            brakeOn();
            releaseOff();
            if (millis() - timestamp >
                (function == FUNCTION_BRAKE ? operationTimeoutBrake : operationTimeoutAntiSlide))
            {
                state = ERROR_BRAKE_TIMEOUT;
            }
            else if (millis() - timestamp > detectionInterval && releaseStatus == SWITCH_IN_PLACE)
            {
                state = ERROR_RELEASE_SWITCH_ON;
            }
            else if (switchStatus == CONTROL_LOCAL)
            {
                state = STATE_STOP_LOCAL;
            }
            else if (brakeStatus == SWITCH_IN_PLACE)
            {
                push_away_stable = false;
                unified_flag_stable = true;
                push_away_counter = 0;
                unified_flag_counter = 0;
                state = STATE_STOP_AT_BRAKE_REMOTE;
            }
            break;
        case STATE_RELEASING_REMOTE:
            releaseOn();
            brakeOff();
            if (millis() - timestamp >
                (function == FUNCTION_BRAKE ? operationTimeoutBrake : operationTimeoutAntiSlide))
            {
                state = ERROR_RELEASE_TIMEOUT;
            }
            else if (millis() - timestamp > detectionInterval && brakeStatus == SWITCH_IN_PLACE)
            {
                state = ERROR_BRAKE_SWITCH_ON;
            }
            else if (switchStatus == CONTROL_LOCAL)
            {
                state = STATE_STOP_LOCAL;
            }
            else if (releaseStatus == SWITCH_IN_PLACE)
            {
                timestamp = millis();
                state = STATE_STOP_AT_RELEASE_REMOTE;
            }
            break;
        case STATE_STOP_LOCAL:
            releaseOff();
            brakeOff();
            if (xSemaphoreTake(xErrorSemaphore, 5) == pdTRUE)
            {
                errorGlobal &= 0b1010;
                ledUpdate(errorGlobal);
                xSemaphoreGive(xErrorSemaphore);
            }
            if (switchStatus == CONTROL_REMOTE)
            {
                state = STATE_INIT;
            }
            else if (controlButton == BUTTON_PRESSED && brakeButton == BUTTON_PRESSED &&
                releaseButton == BUTTON_NOT_PRESSED)
            {
                state = STATE_BRAKING_LOCAL;
            }
            else if (controlButton == BUTTON_PRESSED && brakeButton == BUTTON_NOT_PRESSED &&
                releaseButton == BUTTON_PRESSED)
            {
                state = STATE_RELEASING_LOCAL;
            }
            break;
        case STATE_BRAKING_LOCAL:
            brakeOn();
            releaseOff();
            if (switchStatus == CONTROL_REMOTE)
            {
                state = STATE_INIT;
            }
            else if (controlButton == BUTTON_NOT_PRESSED || brakeButton == BUTTON_NOT_PRESSED ||
                releaseButton == BUTTON_PRESSED)
            {
                state = STATE_STOP_LOCAL;
            }
            break;
        case STATE_RELEASING_LOCAL:
            releaseOn();
            brakeOff();
            if (switchStatus == CONTROL_REMOTE)
            {
                state = STATE_INIT;
            }
            else if (controlButton == BUTTON_NOT_PRESSED || brakeButton == BUTTON_PRESSED ||
                releaseButton == BUTTON_NOT_PRESSED)
            {
                state = STATE_STOP_LOCAL;
            }
            break;
        case STATE_PUSH_AWAY:
        case WARNING_NOT_IN_PLACE:
            brakeOff();
            releaseOff();
            if (xSemaphoreTake(xErrorSemaphore, 5) == pdTRUE)
            {
                errorGlobal |= 0b0001;
                ledUpdate(errorGlobal);
                xSemaphoreGive(xErrorSemaphore);
            }
            if (switchStatus == CONTROL_LOCAL)
            {
                state = STATE_STOP_LOCAL;
            }
            break;
        case ERROR_BOTH_SWITCH_ON:
        case ERROR_RELEASE_SWITCH_ON:
        case ERROR_BRAKE_SWITCH_OFF:
        case ERROR_BRAKE_SWITCH_ON:
        case ERROR_RELEASE_SWITCH_OFF:
        case ERROR_BRAKE_TIMEOUT:
        case ERROR_RELEASE_TIMEOUT:
        case ERROR_NOT_UNIFIED_RELEASE:
        case ERROR_NOT_UNIFIED_BRAKE:
            brakeOff();
            releaseOff();
            if (xSemaphoreTake(xErrorSemaphore, 5) == pdTRUE)
            {
                errorGlobal |= 0b0100;
                ledUpdate(errorGlobal);
                xSemaphoreGive(xErrorSemaphore);
            }
            if (switchStatus == CONTROL_LOCAL)
            {
                state = STATE_STOP_LOCAL;
            }
        default:
            break;
        }
#ifdef SERIAL_DEBUG
        debugSerial.printf("State: %d\r\n", state);
        debugSerial.printf("Switch Status: %s\r\n", switchStatus == CONTROL_LOCAL ? "Local" : "Remote");
        debugSerial.printf("Brake Status: %s\r\n", brakeStatus == SWITCH_IN_PLACE ? "In Place" : "Not In Place");
        debugSerial.printf("Release Status: %s\r\n",
                           releaseStatus == SWITCH_IN_PLACE ? "In Place" : "Not In Place");
        debugSerial.printf("Brake Command: %s\r\n", brakeCommand == COMMAND_ENABLE ? "Enable" : "Disable");
        debugSerial.printf("Release Command: %s\r\n", releaseCommand == COMMAND_ENABLE ? "Enable" : "Disable");
        debugSerial.printf("Brake Button: %s\r\n", brakeButton == BUTTON_PRESSED ? "Pressed" : "Not Pressed");
        debugSerial.printf("Release Button: %s\r\n", releaseButton == BUTTON_PRESSED ? "Pressed" : "Not Pressed");
        debugSerial.printf("Control Button: %s\r\n", controlButton == BUTTON_PRESSED ? "Pressed" : "Not Pressed");
        debugSerial.println();
#endif
        vTaskDelay(10 / portTICK_RATE_MS);
    }
}

void brakeOn()
{
    pinMode(BRAKE_ENABLE_PIN, OUTPUT);
    digitalWrite(BRAKE_ENABLE_PIN, LOW);
}

void brakeOff()
{
    pinMode(BRAKE_ENABLE_PIN, INPUT_PULLUP);
}

void releaseOn()
{
    pinMode(RELEASE_ENABLE_PIN, OUTPUT);
    digitalWrite(RELEASE_ENABLE_PIN, LOW);
}

void releaseOff()
{
    pinMode(RELEASE_ENABLE_PIN, INPUT_PULLUP);
}

void ledOn(uint8_t r, uint8_t g, uint8_t b)
{
    pinMode(LED_R_PIN, OUTPUT);
    pinMode(LED_G_PIN, OUTPUT);
    pinMode(LED_B_PIN, OUTPUT);
    digitalWrite(LED_B_PIN, !b);
    digitalWrite(LED_G_PIN, !g);
    digitalWrite(LED_R_PIN, !r);
}

void ledOff()
{
    pinMode(LED_R_PIN, INPUT_PULLUP);
    pinMode(LED_G_PIN, INPUT_PULLUP);
    pinMode(LED_B_PIN, INPUT_PULLUP);
}

void ledUpdate(uint8_t error)
{
    if ((error & 0b0100) != 0)
    {
        ledOn(HIGH, LOW, LOW); // Red
    }
    else if ((error & 0b0010) != 0)
    {
        ledOn(LOW, LOW, HIGH); // Blue
    }
    else if ((error & 0b0001) != 0)
    {
        ledOn(LOW, HIGH, LOW); // Green
    }
    else
    {
        ledOff();
    }
}

void readFunction()
{
    function = digitalRead(FUNCTION_SELECT_PIN);
#ifdef SERIAL_DEBUG
    debugSerial.printf("Function: %s.\r\n", function == FUNCTION_BRAKE ? "Brake" : "Anti-Slide");
#endif
}

void readID()
{
    trackID = 0;
    deviceID = 0;
    for (uint8_t i = 0; i < 7; i++)
    {
        trackID |= (!digitalRead(TRACK_ID_PIN[i])) << i;
    }
    for (uint8_t i = 0; i < 2; i++)
    {
        deviceID |= (!digitalRead(DEVICE_ID_PIN[i])) << i;
    }
#ifdef SERIAL_DEBUG
    debugSerial.printf("Track ID: %d.\r\n", trackID);
    debugSerial.printf("DEVICE ID: %d.\r\n", deviceID);
#endif
}

uint8_t readReleaseStatus()
{
    static uint8_t counter = 0;
    static uint8_t stable_status = HIGH;
    uint8_t current_status = digitalRead(RELEASE_STATUS_PIN);

    if (current_status != stable_status)
    {
        counter = (counter < 0xFF) ? counter + 1 : debounce_threshold;

        if (counter >= debounce_threshold)
        {
            stable_status = current_status;
            counter = 0;
        }
    }
    else
    {
        counter = 0;
    }
    return stable_status == LOW;
}

uint8_t readBrakeStatus()
{
    static uint8_t counter = 0;
    static uint8_t stable_status = HIGH;
    uint8_t current_status = digitalRead(BRAKE_STATUS_PIN);

    if (current_status != stable_status)
    {
        counter = (counter < 0xFF) ? counter + 1 : debounce_threshold;

        if (counter >= debounce_threshold)
        {
            stable_status = current_status;
            counter = 0;
        }
    }
    else
    {
        counter = 0;
    }
    return stable_status == LOW;
}

uint8_t readSwitchStatus()
{
    static uint8_t counter = 0;
    static uint8_t stable_status = HIGH;
    uint8_t current_status = digitalRead(SWITCH_STATUS_PIN);

    if (current_status != stable_status)
    {
        counter = (counter < 0xFF) ? counter + 1 : debounce_threshold;

        if (counter >= debounce_threshold)
        {
            stable_status = current_status;
            counter = 0;
        }
    }
    else
    {
        counter = 0;
    }
    return stable_status == LOW;
}

uint8_t readControlButton()
{
    static uint8_t counter = 0;
    static uint8_t stable_status = HIGH;
    uint8_t current_status = digitalRead(CONTROL_BUTTON_PIN);

    if (current_status != stable_status)
    {
        counter = (counter < 0xFF) ? counter + 1 : debounce_threshold;

        if (counter >= debounce_threshold)
        {
            stable_status = current_status;
            counter = 0;
        }
    }
    else
    {
        counter = 0;
    }
    return stable_status == LOW;
}

uint8_t readBrakeButton()
{
    static uint8_t counter = 0;
    static uint8_t stable_status = HIGH;
    uint8_t current_status = digitalRead(BRAKE_BUTTON_PIN);

    if (current_status != stable_status)
    {
        counter = (counter < 0xFF) ? counter + 1 : debounce_threshold;

        if (counter >= debounce_threshold)
        {
            stable_status = current_status;
            counter = 0;
        }
    }
    else
    {
        counter = 0;
    }
    return stable_status == LOW;
}

uint8_t readReleaseButton()
{
    static uint8_t counter = 0;
    static uint8_t stable_status = HIGH;
    uint8_t current_status = digitalRead(RELEASE_BUTTON_PIN);

    if (current_status != stable_status)
    {
        counter = (counter < 0xFF) ? counter + 1 : debounce_threshold;

        if (counter >= debounce_threshold)
        {
            stable_status = current_status;
            counter = 0;
        }
    }
    else
    {
        counter = 0;
    }
    return stable_status == LOW;
}

uint8_t readIOStateLow()
{
    static uint8_t counter[8] = {0};
    static uint8_t stable_status[8] = {HIGH, HIGH, HIGH, HIGH, HIGH, HIGH, HIGH, HIGH};

    for (uint8_t i = 0; i < 8; i++)
    {
        uint8_t current_status = digitalRead(IO_PIN_LOW[i]);
        if (current_status != stable_status[i])
        {
            counter[i] = (counter[i] < 0xFF) ? counter[i] + 1 : debounce_threshold;

            if (counter[i] >= debounce_threshold)
            {
                stable_status[i] = current_status;
                counter[i] = 0;
            }
        }
        else
        {
            counter[i] = 0;
        }
    }

    uint8_t ioState = 0;
    for (uint8_t i = 0; i < 8; i++)
    {
        ioState |= (!stable_status[i]) << i;
    }

    return ioState;
}

uint8_t readIOStateHigh()
{
    static uint8_t counter[8] = {0};
    static uint8_t stable_status[8] = {HIGH, LOW, LOW, LOW, LOW, LOW, LOW, LOW};

    for (uint8_t i = 0; i < 1; i++)
    {
        uint8_t current_status = digitalRead(IO_PIN_HIGH[i]);
        if (current_status != stable_status[i])
        {
            counter[i] = (counter[i] < 0xFF) ? counter[i] + 1 : debounce_threshold;

            if (counter[i] >= debounce_threshold)
            {
                stable_status[i] = current_status;
                counter[i] = 0;
            }
        }
        else
        {
            counter[i] = 0;
        }
    }

    uint8_t ioState = 0;
    for (uint8_t i = 0; i < 1; i++)
    {
        ioState |= (!stable_status[i]) << i;
    }

    return ioState;
}

bool parseByte(unsigned char byte, volatile uint8_t& command)
{
    static unsigned char checksum = 0;
    static unsigned char step = 0;
    static uint8_t buffer = PACKET_COMMAND_NULL;

    uint8_t direction;
    uint8_t functionSelect;
    uint8_t switchStatus;
    uint8_t device;
    switch (step)
    {
    case 0:
        if (byte == PACKET_HEADER)
        {
            checksum = PACKET_HEADER;
            buffer = PACKET_COMMAND_NULL;
            step++;
        }
        break;
    case 1:
        checksum ^= byte;
        direction = (byte & 0b11000000) >> 6;
        functionSelect = (byte & 0b00110000) >> 4;
        switchStatus = (byte & 0b00001100) >> 2;
        device = (byte & 0b00000011);
        if (direction == PACKET_DOWNSTREAM &&
            (functionSelect == (function == FUNCTION_BRAKE ? PACKET_FUNCTION_BRAKE : PACKET_FUNCTION_ANTI_SLIDE) ||
                functionSelect == 0x00) &&
            switchStatus == PACKET_CONTROL_REMOTE &&
            (device == deviceID || device == 0x00))
        {
            step++;
        }
        else
        {
            step = 0;
        }
        break;
    case 2:
        checksum ^= byte;
        if (byte == trackID || byte == 0x00)
        {
            step++;
        }
        else
        {
            step = 0;
        }
        break;
    case 3:
        checksum ^= byte;
        if (byte < PACKET_COMMAND_NULL)
        {
            buffer = byte;
            step++;
        }
        else
        {
            step = 0;
        }
        break;
    case 4:
    case 5:
        checksum ^= byte;
        step++;
        break;
    case 6:
        checksum ^= byte;
        if (byte == PACKET_TAIL)
        {
            step++;
        }
        else
        {
            step = 0;
        }
        break;
    case 7:
        step = 0;
        if (byte == checksum || byte == 0xFF)
        {
            switch (buffer)
            {
            case PACKET_COMMAND_REQUEST:
                command = COMMAND_REQUEST;
                break;
            case PACKET_COMMAND_BRAKE:
                command = COMMAND_BRAKE;
                break;
            case PACKET_COMMAND_RELEASE:
                command = COMMAND_RELEASE;
                break;
            default:
                command = COMMAND_NULL;
            }
            return true;
        }
    default:
        step = 0;
        break;
    }
    command = COMMAND_NULL;
    return false;
}
