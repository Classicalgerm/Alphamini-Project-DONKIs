#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <NTPClient.h>

// ---- WiFi SSID and PASSWORD ----
const char* ssid = "OnePlus 12R";
const char* password = "**********";

// ---- LCD setup ----
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ---- NTP setup ----
WiFiUDP ntpUDP;
const long utcOffsetInSeconds = 8 * 3600; // Singapore Time UTC+8
NTPClient timeClient(ntpUDP, "pool.ntp.org", utcOffsetInSeconds);

// ---- Buzzer ----
#define BUZZER D5  // GPIO14

// ---- Alarm Time ----
int alarmHour = 7;     // set your desired alarm hour (24-hour format)
int alarmMinute = 30;  // set your desired alarm minute
bool alarmTriggered = false;

void setup() {
  Serial.begin(115200);

  // LCD init
  lcd.init();
  lcd.backlight();
  lcd.print("Connecting WiFi");

  // Connect WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    lcd.print(".");
    Serial.print(".");
  }

  lcd.clear();
  lcd.print("WiFi Connected!");
  delay(1000);
  lcd.clear();

  // Start NTP client
  timeClient.begin();

  // Buzzer pin
  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);
}

void loop() {
  timeClient.update();

  // Get time
  unsigned long epochTime = timeClient.getEpochTime();
  time_t rawTime = epochTime;
  struct tm *ptm = localtime(&rawTime);

  int hour = ptm->tm_hour;
  int minute = ptm->tm_min;
  int second = ptm->tm_sec;
  int day = ptm->tm_mday;
  int month = ptm->tm_mon + 1;
  int year = ptm->tm_year + 1900;

  // ---- Display time on LCD ----
  lcd.setCursor(0, 0);
  // Blink the colon every second
  if (second % 2 == 0)
    lcd.printf("%02d:%02d:%02d", hour, minute, second);
  else
    lcd.printf("%02d %02d %02d", hour, minute, second);

  lcd.setCursor(0, 1);
  lcd.printf("%02d/%02d/%04d", day, month, year);

  // ---- Alarm Logic ----
  if (hour == alarmHour && minute == alarmMinute && !alarmTriggered) {
    lcd.clear();
    lcd.print("⏰ Alarm Ringing!");
    for (int i = 0; i < 5; i++) { // 5 beeps
      tone(BUZZER, 1000);
      delay(500);
      noTone(BUZZER);
      delay(500);
    }
    alarmTriggered = true;
    lcd.clear();
  }

  // Reset alarm after that minute has passed
  if (minute != alarmMinute) {
    alarmTriggered = false;
  }

  delay(1000);
}
