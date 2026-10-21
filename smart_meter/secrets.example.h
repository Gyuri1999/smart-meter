// Αντέγραψε αυτό το αρχείο σε "secrets.h" και συμπλήρωσε τα δικά σου στοιχεία.
// Copy this file to "secrets.h" and fill in your own values.
#pragma once

static const char *WIFI_SSID = "your-wifi-name";
static const char *WIFI_PASS = "your-wifi-password";

static const char *MQTT_HOST = "192.168.1.10";   // IP του broker / broker IP
static const uint16_t MQTT_PORT = 1883;
static const char *MQTT_USER = "";               // "" αν δεν χρειάζεται / if not needed
static const char *MQTT_PASS = "";

// Δωρεάν token από / free token from https://transparency.entsoe.eu
// Κενό = σταθερή τιμή FALLBACK_PRICE / empty = fixed FALLBACK_PRICE
static const char *ENTSOE_TOKEN = "";
