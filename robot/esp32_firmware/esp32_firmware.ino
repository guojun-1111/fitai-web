/**
 * FitAI 桌面健康机器人 — ESP32-S3 固件
 *
 * 功能：
 *  - 传感器采集：红外人体(HC-SR501)、激光测距(VL53L0X)、称重(HX711)、电池电压
 *  - 执行器控制：舵机 × 2 (PCA9685/PWM)、WS2812 LED 灯带、蜂鸣器
 *  - 串口通信：JSON 行协议与主控（树莓派/核心板）通信
 *
 * 编译环境：Arduino IDE 或 PlatformIO
 * 依赖库：
 *   - Adafruit PWM Servo Driver Library（如果使用 PCA9685）
 *   - Adafruit NeoPixel
 *   - VL53L0X (by Pololu)
 *   - HX711 (by Bogdan Necula)
 *   - ArduinoJson (by Benoit Blanchon)
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <WiFi.h>  // ESP32-S3 自带

// ======== 引脚定义（根据你的底板设计修改） ========

// 传感器
#define PIN_IR_SENSOR     4    // HC-SR501 红外人体传感器（数字量）
#define PIN_ULTRASONIC_TRIG  5   // HC-SR04 Trig（超声波，备选）
#define PIN_ULTRASONIC_ECHO  6   // HC-SR04 Echo
#define PIN_HX711_DOUT    7    // HX711 称重传感器 DOUT
#define PIN_HX711_SCK     8    // HX711 称重传感器 SCK
#define PIN_BATTERY_ADC   9    // 电池电压分压检测（ADC1_CH0）

// 执行器
#define PIN_SERVO_HEAD    10   // 头部舵机（PWM）
#define PIN_SERVO_ARM     11   // 手臂舵机（PWM）
#define PIN_LED_STRIP     12   // WS2812 LED 灯带
#define PIN_BUZZER        13   // 无源蜂鸣器

// I2C（VL53L0X 激光测距用）
#define I2C_SDA           14
#define I2C_SCL           15

// 串口（与主控通信）
#define UART_MAIN         Serial2  // ESP32-S3 的 UART2（GPIO16=RX, GPIO17=TX）
#define BAUD_MAIN         115200

// ======== 常量 ========
#define LED_NUM_LEDS      16      // WS2812 LED 数量
#define SERVO_MIN_PULSE   500     // 舵机最小脉宽 (us)
#define SERVO_MAX_PULSE   2500    // 舵机最大脉宽 (us)
#define SERVO_FREQ        50      // 舵机 PWM 频率 (Hz)
#define BATTERY_R1        100.0   // 分压电阻 R1 (kΩ)
#define BATTERY_R2        100.0   // 分压电阻 R2 (kΩ)
#define HEARTBEAT_MS      2000    // 心跳间隔

// ======== 全局对象 ========

#include <Adafruit_NeoPixel.h>
Adafruit_NeoPixel strip(LED_NUM_LEDS, PIN_LED_STRIP, NEO_GRB + NEO_KHZ800);

// HX711（简化读取，实际使用时引入 HX711 库）
#include "HX711.h"
HX711 scale;

// VL53L0X
#include <VL53L0X.h>
VL53L0X tof_sensor;

// ======== 状态变量 ========
bool ir_present = false;
float distance_cm = 0.0;
float weight_g = 0.0;
int battery_mv = 0;
int head_servo_angle = 90;
int arm_servo_angle = 90;
uint32_t last_heartbeat = 0;
uint32_t last_buzz = 0;
String current_emotion = "smile";
StaticJsonDocument<256> rx_doc;     // 接收缓冲区
StaticJsonDocument<256> tx_doc;     // 发送缓冲区

// ======== 初始化 ========

void setup() {
  Serial.begin(115200);
  Serial.println("[ESP32] FitAI 桌面机器人固件启动...");

  UART_MAIN.begin(BAUD_MAIN, SERIAL_8N1, 16, 17);

  // 初始化引脚
  pinMode(PIN_IR_SENSOR, INPUT);
  pinMode(PIN_ULTRASONIC_TRIG, OUTPUT);
  pinMode(PIN_ULTRASONIC_ECHO, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_ULTRASONIC_TRIG, LOW);

  // 初始化 I2C
  Wire.begin(I2C_SDA, I2C_SCL);

  // 初始化 VL53L0X 激光测距
  tof_sensor.setTimeout(500);
  if (tof_sensor.init()) {
    tof_sensor.startContinuous();
    Serial.println("[OK] VL53L0X 激光测距已就绪");
  } else {
    Serial.println("[WARN] VL53L0X 未检测到，将使用超声波测距");
  }

  // 初始化 HX711 称重传感器
  scale.begin(PIN_HX711_DOUT, PIN_HX711_SCK);
  // 注意：需要先校准！详见 calibrate_scale() 函数
  scale.set_scale(2280.f);  // 校准因子（每克 2280 个原始值，需实测调整）
  scale.tare();              // 去皮
  Serial.println("[OK] HX711 称重传感器已就绪");

  // 初始化舵机 PWM
  ledcSetup(0, SERVO_FREQ, 16);   // 通道0 → 头部舵机
  ledcAttachPin(PIN_SERVO_HEAD, 0);
  ledcSetup(1, SERVO_FREQ, 16);   // 通道1 → 手臂舵机
  ledcAttachPin(PIN_SERVO_ARM, 1);
  set_servo(0, 90);
  set_servo(1, 90);

  // 初始化 WS2812
  strip.begin();
  strip.setBrightness(40);
  strip.show();
  set_emotion_led("smile");

  // 初始化 ADC（电池电压）
  analogReadResolution(12);       // ESP32-S3 ADC 12bit
  analogSetAttenuation(ADC_11db); // 0-3.3V 量程

  Serial.println("[ESP32] 就绪！");
}

// ======== 主循环 ========

void loop() {
  // 1. 读取传感器
  read_sensors();

  // 2. 发送传感器数据（有变化时发送，或心跳周期到了发摘要）
  uint32_t now = millis();
  if (now - last_heartbeat >= HEARTBEAT_MS) {
    send_heartbeat();
    last_heartbeat = now;
  }

  // 3. 处理来自主控的指令
  while (UART_MAIN.available()) {
    String line = UART_MAIN.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      handle_command(line);
    }
  }

  // 4. LED 动画更新
  update_led_animation();

  // 5. 蜂鸣器自动关闭
  if (digitalRead(PIN_BUZZER) == HIGH && now - last_buzz > 500) {
    digitalWrite(PIN_BUZZER, LOW);
  }

  delay(20);
}

// ======== 传感器读取 ========

void read_sensors() {
  // 红外人体传感器
  ir_present = (digitalRead(PIN_IR_SENSOR) == HIGH);

  // 激光测距（VL53L0X）或超声波测距（备选）
  if (!tof_sensor.timeoutOccurred()) {
    distance_cm = tof_sensor.readRangeContinuousMillimeters() / 10.0;
  } else {
    distance_cm = read_ultrasonic();
  }

  // 称重传感器
  if (scale.is_ready()) {
    weight_g = scale.get_units(3);  // 3 次取平均
  }

  // 电池电压
  int adc = analogRead(PIN_BATTERY_ADC);
  float voltage_adc = (adc / 4095.0) * 3.3;
  // 分压比：Vbat → R1 → ADC → R2 → GND,  Vbat = VADC * (R1+R2)/R2
  float vbat = voltage_adc * ((BATTERY_R1 + BATTERY_R2) / BATTERY_R2);
  battery_mv = (int)(vbat * 1000);
}

float read_ultrasonic() {
  // HC-SR04 超声波测距（备选）
  digitalWrite(PIN_ULTRASONIC_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_ULTRASONIC_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_ULTRASONIC_TRIG, LOW);
  long duration = pulseIn(PIN_ULTRASONIC_ECHO, HIGH, 30000); // 30ms 超时
  if (duration == 0) return 0;
  return duration * 0.0343 / 2.0;  // 声速 343m/s
}

// ======== 串口通信 ========

void send_heartbeat() {
  tx_doc.clear();
  tx_doc["event"] = "sensor";
  tx_doc["ir"] = ir_present ? 1 : 0;
  tx_doc["distance_cm"] = distance_cm;
  tx_doc["weight_g"] = weight_g;
  tx_doc["battery_mv"] = battery_mv;
  serializeJson(tx_doc, UART_MAIN);
  UART_MAIN.println();
}

void handle_command(String line) {
  DeserializationError err = deserializeJson(rx_doc, line);
  if (err) {
    Serial.printf("[ESP32] JSON 解析失败: %s\n", line.c_str());
    return;
  }

  String cmd = rx_doc["cmd"] | "";

  if (cmd == "ping") {
    // 心跳响应
    tx_doc.clear();
    tx_doc["event"] = "heartbeat";
    tx_doc["battery_mv"] = battery_mv;
    serializeJson(tx_doc, UART_MAIN);
    UART_MAIN.println();

  } else if (cmd == "servo") {
    int head = rx_doc["head"] | 90;
    int arm = rx_doc["arm"] | 90;
    set_servo(0, head);
    set_servo(1, arm);

  } else if (cmd == "led") {
    int r = rx_doc["r"] | 255;
    int g = rx_doc["g"] | 255;
    int b = rx_doc["b"] | 255;
    fill_led(r, g, b);

  } else if (cmd == "led_matrix") {
    String emotion = rx_doc["emotion"] | "smile";
    current_emotion = emotion;
    set_emotion_led(emotion);

  } else if (cmd == "beep") {
    int freq = rx_doc["freq"] | 2000;
    int dur = rx_doc["dur"] | 200;
    if (freq > 0 && dur > 0) {
      tone(PIN_BUZZER, freq, dur);
      last_buzz = millis();
    }
  }
}

// ======== 执行器控制 ========

void set_servo(int channel, int angle) {
  angle = constrain(angle, 0, 180);
  // 角度 → 脉宽 → duty 值
  int pulse_us = map(angle, 0, 180, SERVO_MIN_PULSE, SERVO_MAX_PULSE);
  // PWM duty: duty_cycle = pulse_us / period_us * 65536
  // period_us = 1000000 / SERVO_FREQ = 20000us
  int duty = (int)((long)pulse_us * 65536 / 20000);
  ledcWrite(channel, duty);
}

void fill_led(int r, int g, int b) {
  for (int i = 0; i < LED_NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(r, g, b));
  }
  strip.show();
}

void set_emotion_led(String emotion) {
  uint32_t color;
  if (emotion == "smile")       color = strip.Color(0, 255, 100);
  else if (emotion == "worried")  color = strip.Color(255, 180, 0);
  else if (emotion == "sleep")    color = strip.Color(50, 50, 150);
  else if (emotion == "surprised") color = strip.Color(0, 200, 255);
  else if (emotion == "confetti")  color = strip.Color(255, 100, 255);
  else                           color = strip.Color(255, 255, 255);

  for (int i = 0; i < LED_NUM_LEDS; i++) {
    strip.setPixelColor(i, color);
  }
  strip.show();
}

// ======== LED 呼吸动画 ========

void update_led_animation() {
  static uint32_t last_anim = 0;
  uint32_t now = millis();
  if (now - last_anim < 50) return;
  last_anim = now;

  // 呼吸效果：亮度从 30% 到 100% 之间正弦变化
  static int brightness = 100;
  static int direction = -1;
  brightness += direction;
  if (brightness <= 60) direction = 1;
  if (brightness >= 120) direction = -1;

  strip.setBrightness(constrain(brightness, 60, 120));
  strip.show();
}

// ======== 称重传感器校准（手动触发） ========

/**
 * 校准步骤：
 * 1. 空盘状态 → 调用 scale.tare()
 * 2. 放一个已知重量物体（如 100g 砝码）
 * 3. 读 raw 值 → scale.get_units(10)
 * 4. 计算 calibration_factor = raw / known_weight
 * 5. 将 calibration_factor 填入 scale.set_scale(factor)
 */
void calibrate_scale() {
  Serial.println("===== HX711 校准模式 =====");
  Serial.println("1. 确保秤盘是空的");
  Serial.println("2. 输入 'TARE' 进行去皮");
  Serial.println("3. 放上已知重量的物体（如 100g 砝码）");
  Serial.println("4. 输入已知重量值（数字即可）");
  Serial.println("=========================");

  scale.tare();
  Serial.println("[OK] 已去皮，请放砝码后输入重量值...");

  while (true) {
    if (Serial.available()) {
      String input = Serial.readStringUntil('\n');
      input.trim();
      if (input.equalsIgnoreCase("TARE")) {
        scale.tare();
        Serial.println("[OK] 已去皮");
      } else {
        float known = input.toFloat();
        if (known > 0) {
          float raw = scale.get_units(10);
          float factor = raw / known;
          scale.set_scale(factor);
          Serial.printf("[OK] 校准完成！factor = %.1f\n", factor);
          Serial.println("退出校准模式...");
          break;
        }
      }
    }
    delay(100);
  }
}
