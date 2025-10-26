#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <NTPClient.h>

// ---- WiFi credentials ----
const char* ssid = "OnePlus 12R";
const char* password = "z29jy8u8";

// ---- LCD setup ----
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ---- NTP setup ----
WiFiUDP ntpUDP;
const long utcOffsetInSeconds = 8 * 3600; // Singapore Time UTC+8
NTPClient timeClient(ntpUDP, "pool.ntp.org", utcOffsetInSeconds);

// ---- Buzzer ----
#define BUZZER 14  // D5 = GPIO14

// ---- Alarm time ----
int alarmHour = 8;
int alarmMinute = 0;
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

  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);
}

void loop() {
  timeClient.update();

  // Get epoch time adjusted for Singapore
  unsigned long epochTime = timeClient.getEpochTime();

  // Convert to local time
  time_t rawTime = epochTime;
  struct tm *ptm = localtime(&rawTime);

  int hour = ptm->tm_hour;
  int minute = ptm->tm_min;
  int second = ptm->tm_sec;
  int day = ptm->tm_mday;
  int month = ptm->tm_mon + 1;
  int year = ptm->tm_year + 1900;

  // Display on LCD
  lcd.setCursor(0, 0);
  lcd.printf("%02d:%02d:%02d", hour, minute, second);

  lcd.setCursor(0, 1);
  lcd.printf("%02d/%02d/%04d", day, month, year);

  // Alarm logic
  if (hour == alarmHour && minute == alarmMinute && !alarmTriggered) {
    tone(BUZZER, 1000);
    lcd.clear();
    lcd.print("Alarm Ringing!");
    delay(5000);
    noTone(BUZZER);
    alarmTriggered = true;
  }

  if (minute != alarmMinute) {
    alarmTriggered = false;
  }

  delay(1000);
}
