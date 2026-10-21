/* ============================================================================
   SMART METER  --  ESP32-C3 Mini
   ----------------------------------------------------------------------------
   Αισθητήρας τάσης  : ZMPT101B (module με τελεστικό + ποτενσιόμετρο) -> GPIO2
   Αισθητήρας ρεύματος: SCT-013 30A/1V (έξοδος τάσης, ΜΕ εσωτερικό burden)
                        -> GPIO0, με διαιρέτη τάσης 10k/10k (bias 1.65V)
                        και πυκνωτή 10uF από το μέσο του διαιρέτη προς GND.

   Μετράει: Vrms, Irms, Πραγματική Ισχύ (W), Φαινόμενη (VA), cos(φ), kWh
   και τα δημοσιεύει σε MQTT (με προαιρετικό Home Assistant auto-discovery).

   Απαιτεί τη βιβλιοθήκη: PubSubClient (Nick O'Leary) - Library Manager.

   !!! ΠΡΟΣΟΧΗ: το ZMPT101B συνδέεται στα 230V AC. Δούλεψε με το κύκλωμα
   ΑΠΟΣΥΝΔΕΔΕΜΕΝΟ από το δίκτυο. Μόνωση, κουτί, ασφάλεια.
   ============================================================================ */

// ------------------------------------------------------------ WiFi / MQTT
#define USE_MQTT      1      // 0 = μόνο σειριακή, χωρίς δίκτυο
#define HA_DISCOVERY  1      // 1 = αυτόματη αναγνώριση από Home Assistant

#if USE_MQTT
  #include <WiFi.h>
  #include <WiFiClientSecure.h>
  #include <HTTPClient.h>
  #include <PubSubClient.h>
  #include <time.h>

  // WiFi, MQTT και ENTSO-E token βρίσκονται στο secrets.h (δεν ανεβαίνει στο
  // GitHub). Αντέγραψε το secrets.example.h σε secrets.h και συμπλήρωσέ το.
  #include "secrets.h"

  static const char *MQTT_BASE = "smartmeter";     // ρίζα των topics
  static const uint32_t PUBLISH_EVERY_MS = 5000;   // κάθε πότε δημοσιεύουμε

  // ------------------------------------------- Day-ahead τιμή κιλοβατώρας
  // Το sketch κατεβάζει μία φορά την ημέρα τις ΩΡΙΑΙΕΣ τιμές χονδρικής
  // (day-ahead market, Ελλάδα) από την πλατφόρμα διαφάνειας της ENTSO-E και
  // χρεώνει την κατανάλωση κάθε ώρας με τη δική της τιμή.
  //
  // Δωρεάν token: κάνε λογαριασμό στο https://transparency.entsoe.eu και
  // ζήτα ενεργοποίηση "Restful API access" με email στο transparency@entsoe.eu
  // Αν μείνει κενό (ή πέσει το δίκτυο), χρησιμοποιείται η FALLBACK_PRICE.
  // Το ENTSOE_TOKEN ορίζεται στο secrets.h.
  static const float FALLBACK_PRICE = 0.155f;  // €/kWh χωρίς day-ahead
  static const float PRICE_MARKUP   = 1.0f;    // π.χ. 1.30 για ΦΠΑ+τέλη πάνω στη χονδρική
  static const char *TZ_GREECE = "EET-2EEST,M3.5.0/3,M10.5.0/4";  // ώρα Ελλάδας
#endif

// ---------------------------------------------------------------- ΑΚΡΟΔΕΚΤΕΣ
static const int PIN_VOLT = 2;   // ZMPT101B  OUT  (ADC1_CH2)
static const int PIN_CURR = 0;   // SCT-013   sig  (ADC1_CH0)

// ------------------------------------------------------------- ΒΑΘΜΟΝΟΜΗΣΗ
// VCAL: πόσα Volt AC του δικτύου αντιστοιχούν σε 1 V στο pin.
//       Ξεκίνα με 260.0 και διόρθωσε: VCAL_new = VCAL_old * (Vπολύμετρου / Vσειριακής)
float VCAL = 341.0f;

// ICAL: πόσα Ampere αντιστοιχούν σε 1 V στο pin.
//       SCT-013-030 (30A/1V) απευθείας στο pin  -> 30.0
//       SCT-013-010 (10A/1V)                    -> 10.0
//       Αν έβαλες επιπλέον διαιρέτη ΠΑΝΩ στο σήμα (π.χ. /2) -> διπλασίασε το.
float ICAL = 25.75f;

// PHASECAL: διόρθωση διαφοράς φάσης V/I (1.0 = καμία διόρθωση).
//           Ρύθμισέ το με καθαρά ωμικό φορτίο ώστε cos(φ) ~ 1.00 (τυπικά 0.8 - 2.2)
float PHASECAL = 1.0f;

// PHASE_SHIFT: χονδρική διόρθωση φάσης σε ΟΛΟΚΛΗΡΑ δείγματα (το PHASECAL
// καλύπτει μόνο ±1 δείγμα = ±2.5 μοίρες, πολύ λίγο για τη μετατόπιση που
// εισάγει ο μετασχηματιστής του ZMPT101B). Θετικό = καθυστερεί την τάση.
// Βρες την τιμή με τη σάρωση [sweep] που τρέχει αυτόματα υπό φορτίο.
int PHASE_SHIFT = 12;

// -------------------------------------------------------------- ΔΕΙΓΜΑΤΟΛΗΨΙΑ
static const int      HALF_CYCLES  = 40;     // 39 ημιπερίοδοι = 19.5 περίοδοι @50Hz (~390 ms)
static const uint32_t TIMEOUT_MS   = 1500;   // ασφάλεια αν δεν υπάρχει σήμα
static const double   FILT_TAU     = 1024.0; // σταθερά φίλτρου DC offset
static const float    NOISE_V      = 5.0f;   // κάτω από αυτό -> 0 (Volt)
static const float    NOISE_I      = 0.50f;  // κάτω από αυτό -> 0 (μετρημένος θόρυβος ~0.3 A)

// Αν το clamp είναι ανάποδα και δεν βολεύει να το γυρίσεις (π.χ. μόνιμη
// εγκατάσταση), βάλε 1 και αντιστρέφεται το πρόσημο της ισχύος από λογισμικό.
#define INVERT_CURRENT 0

#define PRINT_DEBUG 1                        // 1 = τύπωσε offsets/δείγματα

// --------------------------------------------------------------- ΜΕΤΑΒΛΗΤΕΣ
static double offsetV = 1650.0;   // DC offset σε mV (ξεκινά στο μισό των 3.3V)
static double offsetI = 1650.0;

static double energy_Wh = 0.0;    // συσσωρευμένη ενέργεια
static uint32_t lastEnergy_ms = 0;

struct Reading {
  float  vrms;          // V
  float  irms;          // A
  float  realPower;     // W
  float  apparentPower; // VA
  float  powerFactor;   // 0..1
  int    samples;
  int    vmin, vmax;    // ακραίες τιμές του καναλιού τάσης, σε mV (έλεγχος clipping)
  bool   ok;
};

// ------------------------------------------------------------------ ΕΞΟΔΟΣ
// Τα μηνύματα βγαίνουν ταυτόχρονα σε δύο σημεία:
//   * USB CDC       -> ο Serial Monitor μέσω του καλωδίου προγραμματισμού
//   * hardware UART0 -> GPIO21 = TX, GPIO20 = RX, για μετατροπέα USB-TTL
// Έτσι βλέπεις την έξοδο ακόμη κι αν το USB CDC δεν είναι διαθέσιμο (π.χ.
// λάθος ρύθμιση "USB CDC On Boot", ή όταν το ESP32 τροφοδοτείται χωριστά).
#define LOG_TO_UART 1
static const uint32_t LOG_BAUD = 115200;

// Αν το USB CDC είναι απενεργοποιημένο, ο Serial ΕΙΝΑΙ ήδη ο UART0 -> μη
// γράψεις δύο φορές στο ίδιο πράγμα.
#if LOG_TO_UART && ARDUINO_USB_CDC_ON_BOOT
  #define LOG_DUAL 1
#else
  #define LOG_DUAL 0
#endif

static void logBegin() {
  Serial.begin(LOG_BAUD);
#if LOG_DUAL
  Serial0.begin(LOG_BAUD);          // GPIO21 TX / GPIO20 RX
#endif
  // Με USB CDC η θύρα ξαναδηλώνεται στο USB μετά το reset. Χωρίς αυτή την
  // αναμονή, τα πρώτα μηνύματα χάνονται πριν προλάβει να συνδεθεί ο monitor.
  while (!Serial && millis() < 3000) delay(10);
  delay(500);
}

static void logf(const char *fmt, ...) {
  char buf[224];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);

  Serial.print(buf);
#if LOG_DUAL
  Serial0.print(buf);
#endif
}

// ------------------------------------------------------------------ ΜΕΤΡΗΣΗ
static Reading measure() {
  Reading r = {0, 0, 0, 0, 0, 0, 5000, 0, false};

  const uint32_t tStart = millis();

  // 1) Warm-up: αφήνουμε το φίλτρο DC offset να "κλειδώσει"
  while (millis() - tStart < 60) {
    offsetV += (analogReadMilliVolts(PIN_VOLT) - offsetV) / FILT_TAU;
    offsetI += (analogReadMilliVolts(PIN_CURR) - offsetI) / FILT_TAU;
  }

  // 2) Κύρια δειγματοληψία, συγχρονισμένη σε μηδενισμούς της τάσης
  const int PBUF = 32;                 // > |PHASE_SHIFT| + 1
  static double pbufV[32], pbufI[32];
  int tick = 0;

  double sumV = 0, sumI = 0, sumP = 0;
  double lastFilteredV = 0;
  int    crossCount = 0;
  int    n = 0;
  bool   started = false;

  // Αρχικοποίηση προσήμου από το τρέχον δείγμα, ώστε ο πρώτος μηδενισμός
  // που θα ανιχνευτεί να είναι πραγματικός -> αθροίζουμε ακέραιο αριθμό
  // ημιπεριόδων και το RMS βγαίνει ακριβές.
  bool   lastSign = (analogReadMilliVolts(PIN_VOLT) - offsetV) > 0;

  while (crossCount < HALF_CYCLES) {
    if (millis() - tStart > TIMEOUT_MS) return r;   // ok = false

    int    rawV = analogReadMilliVolts(PIN_VOLT);
    double sV = rawV;
    double sI = analogReadMilliVolts(PIN_CURR);

    if (rawV < r.vmin) r.vmin = rawV;
    if (rawV > r.vmax) r.vmax = rawV;

    offsetV += (sV - offsetV) / FILT_TAU;
    offsetI += (sI - offsetI) / FILT_TAU;

    double fV = sV - offsetV;      // AC συνιστώσα τάσης  (mV στο pin)
    double fI = sI - offsetI;      // AC συνιστώσα ρεύματος (mV στο pin)

    bool sign = (fV > 0);
    if (sign != lastSign) {
      crossCount++;
      if (!started) {              // ξεκίνα να αθροίζεις από τον 1ο μηδενισμό
        started = true;
        sumV = sumI = sumP = 0;
        n = 0;
      }
    }
    lastSign = sign;

    // Γράψε τα δείγματα στον κυκλικό buffer και διάβασε τα μετατοπισμένα.
    int pi = tick % PBUF;
    pbufV[pi] = fV;
    pbufI[pi] = fI;
    int kv = (PHASE_SHIFT > 0) ?  PHASE_SHIFT : 0;   // καθυστέρηση τάσης
    int ki = (PHASE_SHIFT < 0) ? -PHASE_SHIFT : 0;   // καθυστέρηση ρεύματος
    double v0 = pbufV[(pi - kv     + PBUF) % PBUF];
    double v1 = pbufV[(pi - kv - 1 + PBUF) % PBUF];
    double phaseShiftedV = v1 + PHASECAL * (v0 - v1);   // λεπτή ρύθμιση
    double iShifted      = pbufI[(pi - ki + PBUF) % PBUF];

    if (started && tick >= PBUF) {
      sumV += fV * fV;
      sumI += fI * fI;
      sumP += phaseShiftedV * iShifted;
      n++;
    }
    tick++;
    lastFilteredV = fV;
  }

  if (n < 10) return r;

  // 3) Υπολογισμοί (mV -> V, μετά επί τους συντελεστές βαθμονόμησης)
  double vrms_pin = sqrt(sumV / n) / 1000.0;   // V στο pin
  double irms_pin = sqrt(sumI / n) / 1000.0;   // V στο pin

  r.vrms      = VCAL * vrms_pin;
  r.irms      = ICAL * irms_pin;
  r.realPower = VCAL * ICAL * (sumP / n) / 1.0e6;

  if (r.vrms < NOISE_V) { r.vrms = 0; r.realPower = 0; }
  if (r.irms < NOISE_I) { r.irms = 0; r.realPower = 0; }

#if INVERT_CURRENT
  r.realPower = -r.realPower;
#endif

  r.apparentPower = r.vrms * r.irms;
  r.powerFactor   = (r.apparentPower > 0.5f) ? (r.realPower / r.apparentPower) : 0.0f;
  if (r.powerFactor >  1.0f) r.powerFactor =  1.0f;
  if (r.powerFactor < -1.0f) r.powerFactor = -1.0f;

  r.samples = n;
  r.ok = true;
  return r;
}

// ------------------------------------------------------------- ΔΙΚΤΥΟ MQTT
#if USE_MQTT

static WiFiClient   wifiClient;
static PubSubClient mqtt(wifiClient);

static char devId[8]     = "";   // τα 3 τελευταία byte της MAC, π.χ. "a1b2c3"
static char t_state[64]  = "";   // smartmeter/a1b2c3/state
static char t_avail[64]  = "";   // smartmeter/a1b2c3/availability
static uint32_t lastNetTry  = 0;
static uint32_t lastPublish = 0;

// Στοιχεία που δημοσιεύονται. Το "key" είναι και το πεδίο του JSON.
struct SensorDef {
  const char *key, *name, *unit, *devClass, *stateClass;
};
static const SensorDef SENSORS[] = {
  {"v",  "Τάση",              "V",   "voltage",        "measurement"},
  {"i",  "Ρεύμα",             "A",   "current",        "measurement"},
  {"p",  "Ισχύς",             "W",   "power",          "measurement"},
  {"s",  "Φαινόμενη ισχύς",   "VA",  "apparent_power", "measurement"},
  {"pf", "Συντελεστής ισχύος", "",   "power_factor",   "measurement"},
  {"e",  "Ενέργεια",          "kWh", "energy",         "total_increasing"},
  {"price", "Τιμή κιλοβατώρας", "EUR/kWh", "monetary", "measurement"},
  {"ed",    "Ενέργεια ημέρας",  "kWh",     "energy",   "total"},
  {"cost_h","Κόστος ώρας",      "EUR",     "monetary", "total"},
  {"cost_d","Κόστος ημέρας",    "EUR",     "monetary", "total"},
};

// ------------------------------------------------------ DAY-AHEAD ΤΙΜΗ kWh
// Μία φορά την ημέρα κατεβάζουμε από την πλατφόρμα διαφάνειας της ENTSO-E
// τις ωριαίες τιμές χονδρικής (day-ahead, documentType A44) για την Ελλάδα
// (ζώνη 10YGR-HTSO-----Y). Το κόστος κάθε ώρας υπολογίζεται με την τιμή της
// συγκεκριμένης ώρας. Χωρίς token ή χωρίς κάλυψη, πέφτουμε στη FALLBACK_PRICE.

static float   priceTable[50];      // EUR/MWh, μία ανά ωριαίο Point
static int     priceCount    = 0;
static time_t  priceStartUtc = 0;   // epoch (UTC) της τιμής priceTable[0]
static uint32_t lastPriceFetch = 0;
static bool    timeSynced = false;
static bool    ntpStarted = false;

static double  energyDay_Wh = 0.0;  // Wh της τρέχουσας ημέρας
static double  costHour_EUR = 0.0;  // κόστος τρέχουσας ώρας
static double  costDay_EUR  = 0.0;  // κόστος τρέχουσας ημέρας
static int     curHour = -1, curYday = -1, curYear = -1;

// "YYYY-MM-DDTHH:MMZ" -> epoch (UTC), χωρίς βιβλιοθήκες (days-from-civil).
static time_t parseUtcEpoch(const char *s) {
  int y = (s[0]-'0')*1000 + (s[1]-'0')*100 + (s[2]-'0')*10 + (s[3]-'0');
  int m = (s[5]-'0')*10 + (s[6]-'0');
  int d = (s[8]-'0')*10 + (s[9]-'0');
  int H = (s[11]-'0')*10 + (s[12]-'0');
  int M = (s[14]-'0')*10 + (s[15]-'0');
  y -= (m <= 2);
  long era = (y >= 0 ? y : y - 399) / 400;
  unsigned yoe = (unsigned)(y - era * 400);
  unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  long days = era * 146097L + (long)doe - 719468L;
  return (time_t)(days * 86400L + H * 3600L + M * 60L);
}

// Τρέχουσα τιμή σε EUR/kWh (ή fallback αν δεν υπάρχει κάλυψη).
static float priceNowEURkWh() {
  if (priceCount > 0) {
    long idx = (long)((time(nullptr) - priceStartUtc) / 3600);
    if (idx >= 0 && idx < priceCount)
      return priceTable[idx] / 1000.0f * PRICE_MARKUP;
  }
  return FALLBACK_PRICE;
}

// Κατεβάζει τις ωριαίες day-ahead τιμές για σήμερα + αύριο (τοπική ημέρα).
static bool fetchDayAheadPrices() {
  lastPriceFetch = millis();
  if (!ENTSOE_TOKEN[0]) return false;

  // Ζητάμε από τα τοπικά μεσάνυχτα της σημερινής μέχρι και διαύριο,
  // ώστε ο πίνακας να καλύπτει σίγουρα ολόκληρο το τρέχον 24ωρο.
  time_t now = time(nullptr);
  struct tm lt;
  localtime_r(&now, &lt);
  struct tm m0 = lt;
  m0.tm_hour = 0; m0.tm_min = 0; m0.tm_sec = 0;
  time_t pStart = mktime(&m0);            // τοπικά μεσάνυχτα (σε epoch)
  time_t pEnd   = pStart + 2 * 86400;     // +2 ημέρες

  struct tm ps, pe;
  gmtime_r(&pStart, &ps);
  gmtime_r(&pEnd, &pe);

  char url[352];
  snprintf(url, sizeof(url),
    "https://web-api.tp.entsoe.eu/api?securityToken=%s&documentType=A44"
    "&in_Domain=10YGR-HTSO-----Y&out_Domain=10YGR-HTSO-----Y"
    "&periodStart=%04d%02d%02d%02d%02d&periodEnd=%04d%02d%02d%02d%02d",
    ENTSOE_TOKEN,
    ps.tm_year + 1900, ps.tm_mon + 1, ps.tm_mday, ps.tm_hour, ps.tm_min,
    pe.tm_year + 1900, pe.tm_mon + 1, pe.tm_mday, pe.tm_hour, pe.tm_min);

  WiFiClientSecure tls;
  tls.setInsecure();   // δεν ελέγχουμε πιστοποιητικό - αρκεί για ανάγνωση τιμών
  HTTPClient http;
  http.setTimeout(15000);
  if (!http.begin(tls, url)) { logf("[price] αποτυχία σύνδεσης HTTPS\n"); return false; }

  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    logf("[price] HTTP %d (λάθος/ανενεργό token ή εκτός ορίων αιτημάτων)\n", code);
    http.end();
    return false;
  }

  String body = http.getString();
  http.end();

  // Αρχή της περιόδου: πρώτο <timeInterval><start>...</start>
  int ti = body.indexOf("<timeInterval>");
  int s0 = (ti >= 0) ? body.indexOf("<start>", ti) : -1;
  if (s0 < 0) { logf("[price] δεν βρέθηκε timeInterval στο XML\n"); return false; }
  priceStartUtc = parseUtcEpoch(body.c_str() + s0 + 7);

  // Οι ωριαίες τιμές είναι διαδοχικά <price.amount> (EUR/MWh)
  priceCount = 0;
  int pos = 0;
  const char *TAG = "<price.amount>";
  while (priceCount < (int)(sizeof(priceTable) / sizeof(priceTable[0]))) {
    int a = body.indexOf(TAG, pos);
    if (a < 0) break;
    a += (int)strlen(TAG);
    int b = body.indexOf("</price.amount>", a);
    if (b < 0) break;
    priceTable[priceCount++] = body.substring(a, b).toFloat();
    pos = b;
  }

  logf("[price] %d ωριαίες τιμές από %s", priceCount, ctime(&priceStartUtc));
  logf("[price] τρέχουσα τιμή: %.4f EUR/kWh\n", priceNowEURkWh());
  return priceCount > 0;
}

static void netSetup() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                 // σταθερότερη σύνδεση, λιγότερα stalls
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  uint8_t mac[6];
  WiFi.macAddress(mac);
  snprintf(devId,   sizeof(devId),   "%02x%02x%02x", mac[3], mac[4], mac[5]);
  snprintf(t_state, sizeof(t_state), "%s/%s/state",        MQTT_BASE, devId);
  snprintf(t_avail, sizeof(t_avail), "%s/%s/availability", MQTT_BASE, devId);

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(1024);             // τα payloads του discovery δεν χωράνε στα 256

  logf(" Device ID : %s\n", devId);
  logf(" MQTT topic: %s\n", t_state);
}

#if HA_DISCOVERY
// Στέλνει ένα retained "config" topic ανά μέγεθος, ώστε το Home Assistant να
// φτιάξει μόνο του τις οντότητες κάτω από μία συσκευή.
static void publishDiscovery() {
  char topic[96], payload[640], unitField[48];

  for (const SensorDef &s : SENSORS) {
    snprintf(topic, sizeof(topic),
             "homeassistant/sensor/%s_%s/%s/config", MQTT_BASE, devId, s.key);

    unitField[0] = '\0';
    if (s.unit[0]) snprintf(unitField, sizeof(unitField), "\"unit_of_meas\":\"%s\",", s.unit);

    snprintf(payload, sizeof(payload),
      "{\"name\":\"%s\",\"uniq_id\":\"%s_%s_%s\",\"stat_t\":\"%s\",\"avty_t\":\"%s\","
      "%s\"dev_cla\":\"%s\",\"stat_cla\":\"%s\",\"val_tpl\":\"{{ value_json.%s }}\","
      "\"dev\":{\"ids\":[\"%s_%s\"],\"name\":\"Smart Meter\",\"mf\":\"DIY\","
      "\"mdl\":\"ESP32-C3 + ZMPT101B + SCT-013\"}}",
      s.name, MQTT_BASE, devId, s.key, t_state, t_avail,
      unitField, s.devClass, s.stateClass, s.key,
      MQTT_BASE, devId);

    mqtt.publish(topic, payload, true);   // retained
  }
  logf(" [mqtt] στάλθηκε το Home Assistant discovery\n");
}
#endif

// Μη μπλοκάρουσα διαχείριση σύνδεσης: καλείται συνέχεια από τη loop().
static void netLoop() {
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastNetTry > 10000) {
      lastNetTry = millis();
      logf(" [wifi] επανασύνδεση...\n");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASS);
    }
    return;
  }

  // Μόλις συνδεθεί το WiFi, τύπωσε μία φορά τη διεύθυνση που πήρε.
  static bool ipShown = false;
  if (!ipShown) {
    ipShown = true;
    logf(" [wifi] συνδεθηκε: IP=%s  gateway=%s  RSSI=%d dBm\n",
         WiFi.localIP().toString().c_str(),
         WiFi.gatewayIP().toString().c_str(),
         WiFi.RSSI());
  }

  // Συγχρονισμός ώρας μέσω NTP (ασύγχρονος). Απαραίτητος για τις day-ahead
  // τιμές και για τον μηδενισμό των ημερήσιων μετρητών στα μεσάνυχτα.
  if (!ntpStarted) {
    ntpStarted = true;
    configTzTime(TZ_GREECE, "pool.ntp.org", "time.google.com");
  }
  if (!timeSynced && time(nullptr) > 1700000000) {
    timeSynced = true;
    time_t t = time(nullptr);
    struct tm lt; localtime_r(&t, &lt);
    logf(" [ntp] τοπικη ωρα: %02d:%02d  %02d/%02d/%04d\n",
         lt.tm_hour, lt.tm_min, lt.tm_mday, lt.tm_mon + 1, lt.tm_year + 1900);
  }

  // Day-ahead τιμές: τράβα τες όταν δεν καλύπτουν πλέον το "τώρα", ή όταν
  // μετά τις 15:00 τοπική λείπουν ακόμη οι αυριανές (βγαίνουν ~14:00).
  // Σε αποτυχία ξαναδοκιμάζουμε το νωρίτερο μετά από 30 λεπτά.
  if (timeSynced && ENTSOE_TOKEN[0]) {
    time_t now = time(nullptr);
    time_t coverEnd = priceStartUtc + (time_t)priceCount * 3600;
    struct tm lt; localtime_r(&now, &lt);
    bool need = (priceCount == 0)
             || (now >= coverEnd)
             || (lt.tm_hour >= 15 && coverEnd < now + 32 * 3600);
    if (need && (lastPriceFetch == 0 || millis() - lastPriceFetch > 30UL*60UL*1000UL))
      fetchDayAheadPrices();
  }

  if (!mqtt.connected()) {
    if (millis() - lastNetTry > 5000) {
      lastNetTry = millis();
      char clientId[32];
      snprintf(clientId, sizeof(clientId), "%s_%s", MQTT_BASE, devId);

      // Last Will: αν χαθεί η συσκευή, ο broker στέλνει μόνος του "offline".
      bool ok = mqtt.connect(clientId,
                             MQTT_USER[0] ? MQTT_USER : nullptr,
                             MQTT_PASS[0] ? MQTT_PASS : nullptr,
                             t_avail, 0, true, "offline");
      if (ok) {
        logf(" [mqtt] συνδέθηκε στον %s\n", MQTT_HOST);
        mqtt.publish(t_avail, "online", true);
#if HA_DISCOVERY
        publishDiscovery();
#endif
      } else {
        logf(" [mqtt] αποτυχία (rc=%d)\n", mqtt.state());
      }
    }
    return;
  }

  mqtt.loop();
}

static void publishState(const Reading &r) {
  if (!mqtt.connected()) return;

  char payload[288];
  snprintf(payload, sizeof(payload),
    "{\"v\":%.2f,\"i\":%.3f,\"p\":%.1f,\"s\":%.1f,\"pf\":%.2f,\"e\":%.4f,"
    "\"price\":%.4f,\"ed\":%.4f,\"cost_h\":%.4f,\"cost_d\":%.4f,\"rssi\":%d}",
    r.vrms, r.irms, r.realPower, r.apparentPower, r.powerFactor,
    energy_Wh / 1000.0, priceNowEURkWh(), energyDay_Wh / 1000.0,
    costHour_EUR, costDay_EUR, WiFi.RSSI());

  mqtt.publish(t_state, payload);
}

#endif  // USE_MQTT

// Μετράει ΜΟΝΟ ρεύμα, σε σταθερό παράθυρο χρόνου - δεν εξαρτάται από τους
// μηδενισμούς της τάσης. Χρήσιμο για να ελέγξεις το clamp μόνο του, πριν
// συνδέσεις το ZMPT101B στο δίκτυο. Τυπώνει και το πλάτος σε mV, ώστε να
// ξεχωρίζεις πραγματικό σήμα από θόρυβο.
static void currentOnlyReport(uint32_t windowMs) {
  const uint32_t t0 = millis();
  double sumI = 0;
  int n = 0, mn = 5000, mx = 0;

  while (millis() - t0 < windowMs) {
    int raw = analogReadMilliVolts(PIN_CURR);
    if (raw < mn) mn = raw;
    if (raw > mx) mx = raw;
    offsetI += (raw - offsetI) / FILT_TAU;
    double fI = raw - offsetI;
    sumI += fI * fI;
    n++;
  }

  float irms = (n > 9) ? (float)(ICAL * sqrt(sumI / n) / 1000.0) : 0.0f;
  logf("[I-only] Irms=%.3f A | ptp=%dmV (%d..%d) | %d δείγματα σε %ums -> %.1f kSPS\n",
       irms, mx - mn, mn, mx, n, windowMs, n / (float)windowMs);
}

// ------------------------------------------------------------- ΣΑΡΩΣΗ ΦΑΣΗΣ
// Καταγράφει ~290 ms ωμής κυματομορφής και υπολογίζει το PF για κάθε πιθανή
// μετατόπιση. Με ΩΜΙΚΟ φορτίο, η μετατόπιση που δίνει το μέγιστο PF είναι η
// σωστή τιμή για το PHASE_SHIFT.
#define SWEEP_N      2048
#define SWEEP_MAX_K  24

static void phaseSweep() {
  static float bufV[SWEEP_N], bufI[SWEEP_N];

  uint32_t t0 = micros();
  for (int n = 0; n < SWEEP_N; n++) {
    double sV = analogReadMilliVolts(PIN_VOLT);
    double sI = analogReadMilliVolts(PIN_CURR);
    offsetV += (sV - offsetV) / FILT_TAU;
    offsetI += (sI - offsetI) / FILT_TAU;
    bufV[n] = sV - offsetV;
    bufI[n] = sI - offsetI;
  }
  float fs = SWEEP_N / ((micros() - t0) / 1.0e6f);     // πραγματικός ρυθμός

  const int a = SWEEP_MAX_K, b = SWEEP_N - SWEEP_MAX_K;
  double sv = 0, si = 0;
  for (int n = a; n < b; n++) { sv += (double)bufV[n]*bufV[n]; si += (double)bufI[n]*bufI[n]; }
  double vr = sqrt(sv / (b - a)), ir = sqrt(si / (b - a));

  if (vr < 50.0 || ir < 20.0) { logf("[sweep] πολύ μικρό σήμα - βάλε φορτίο\n"); return; }

  // ΠΡΟΣΟΧΗ: η σάρωση δουλεύει πάνω σε ωμά δείγματα, ΧΩΡΙΣ να εφαρμόζει το
  // PHASE_SHIFT. Άρα το bestK είναι η απόλυτη τιμή που πρέπει να μπει εκεί,
  // όχι κάτι που προστίθεται στην τρέχουσα.
  int bestK = 0; double bestPF = 0, pf0 = 0, pfCur = 0;
  for (int k = -SWEEP_MAX_K; k <= SWEEP_MAX_K; k++) {
    double sp = 0;
    for (int n = a; n < b; n++) sp += (double)bufV[n - k] * bufI[n];
    double pf = sp / ((b - a) * vr * ir);
    if (k == 0)           pf0   = pf;
    if (k == PHASE_SHIFT) pfCur = pf;
    if (fabs(pf) > fabs(bestPF)) { bestPF = pf; bestK = k; }
  }

  logf("[sweep] fs=%.0fHz | αδιορθωτο(0)=%.3f | τρεχον(%d)=%.3f | ΒΕΛΤΙΣΤΟ PHASE_SHIFT=%d -> PF=%.3f (%.1f μοιρες)\n",
       fs, pf0, PHASE_SHIFT, pfCur, bestK, bestPF,
       bestK * 360.0f * 50.0f / fs);
  if (bestPF < 0) logf("[sweep] ΠΡΟΣΟΧΗ: αρνητικο PF -> το clamp ειναι αναποδα\n");
}

// ------------------------------------------------- ΠΡΟΣΩΡΙΝΟ: DUMP ΚΥΜΑΤΟΜΟΡΦΗΣ
// Καταγράφει ~280 ms ωμών δειγμάτων ΜΟΝΟ από το κανάλι ρεύματος και τυπώνει:
//   * Irms ωμό  vs  Irms μετά από median-3 (κόβει μεμονωμένες αιχμές)
//   * ptp ωμό   vs  ptp μετά από median-3, και πόσα δείγματα ήταν αιχμές
//   * τα πρώτα WD_PRINT δείγματα (mV γύρω από το offset) για να φανεί το σχήμα
// Τρέχει μία φορά με WiFi ανοιχτό και μία με WiFi κλειστό, για σύγκριση.
#define WAVE_DUMP   1
#define WD_N        4096
#define WD_PRINT    400        // ~27 ms = λίγο παραπάνω από 1 περίοδο
#define WD_SPIKE_MV 80         // απόκλιση από το median-3 που θεωρείται αιχμή

#if WAVE_DUMP
static int median3(int a, int b, int c) {
  if (a > b) { int t = a; a = b; b = t; }
  if (b > c) { int t = b; b = c; c = t; }
  if (a > b) { int t = a; a = b; b = t; }
  return b;
}

static void waveDump(const char *tag, bool printSamples) {
  static int16_t buf[WD_N];

  uint32_t t0 = micros();
  for (int n = 0; n < WD_N; n++) buf[n] = analogReadMilliVolts(PIN_CURR);
  float fs = WD_N / ((micros() - t0) / 1.0e6f);

  double mean = 0;
  for (int n = 0; n < WD_N; n++) mean += buf[n];
  mean /= WD_N;

  double sRaw = 0, sMed = 0;
  int mnR = 5000, mxR = 0, mnM = 5000, mxM = 0, spikes = 0;
  for (int n = 1; n < WD_N - 1; n++) {
    int raw = buf[n];
    int med = median3(buf[n - 1], buf[n], buf[n + 1]);
    double dr = raw - mean, dm = med - mean;
    sRaw += dr * dr;
    sMed += dm * dm;
    if (raw < mnR) mnR = raw;  if (raw > mxR) mxR = raw;
    if (med < mnM) mnM = med;  if (med > mxM) mxM = med;
    if (abs(raw - med) > WD_SPIKE_MV) spikes++;
  }
  const int cnt = WD_N - 2;
  double rmsRaw = sqrt(sRaw / cnt), rmsMed = sqrt(sMed / cnt);

  logf("[wave:%s] fs=%.0fHz offset=%.0fmV | ωμο: Irms=%.3fA ptp=%dmV ptp/rms=%.2f"
       " | median3: Irms=%.3fA ptp=%dmV ptp/rms=%.2f | αιχμες=%d\n",
       tag, fs, mean,
       ICAL * rmsRaw / 1000.0, mxR - mnR, (mxR - mnR) / rmsRaw,
       ICAL * rmsMed / 1000.0, mxM - mnM, (mxM - mnM) / rmsMed,
       spikes);

  if (!printSamples) return;
  char line[200];
  for (int n = 0; n < WD_PRINT; n += 20) {
    int len = snprintf(line, sizeof(line), "[wave:%s] %4d:", tag, n);
    for (int k = n; k < n + 20 && k < WD_PRINT; k++)
      len += snprintf(line + len, sizeof(line) - len, " %d", (int)(buf[k] - mean));
    logf("%s\n", line);
  }
}

// Σύγκριση WiFi ON / OFF. Μετά το OFF, η netLoop() ξανασυνδέεται μόνη της.
static void waveCompare() {
  waveDump("wifi-on", true);
#if USE_MQTT
  mqtt.disconnect();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  delay(300);
  waveDump("wifi-off", true);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  lastNetTry = millis();
#endif
}
#endif

// -------------------------------------------------------------------- SETUP
void setup() {
  logBegin();

  analogReadResolution(12);                          // 0..4095
  analogSetPinAttenuation(PIN_VOLT, ADC_11db);       // πλήρες εύρος ~0..3.1V
  analogSetPinAttenuation(PIN_CURR, ADC_11db);

  logf("\n");
  logf("==================================================\n");
  logf(" Smart Meter - ESP32-C3 | ZMPT101B(GPIO2) SCT-013(GPIO0)\n");
  logf("==================================================\n");
  logf(" VCAL=%.2f  ICAL=%.2f  PHASECAL=%.2f\n", VCAL, ICAL, PHASECAL);
#if LOG_DUAL
  logf(" Εξοδος    : USB CDC + UART0 (GPIO21=TX, GPIO20=RX) @ %u baud\n", LOG_BAUD);
#else
  logf(" Εξοδος    : UART0 (GPIO21=TX, GPIO20=RX) @ %u baud\n", LOG_BAUD);
#endif
  logf("\n");

#if USE_MQTT
  netSetup();
#endif

  // Μια "τυφλή" μέτρηση για να σταθεροποιηθούν τα φίλτρα
  measure();
  lastEnergy_ms = millis();
}

// --------------------------------------------------------------------- LOOP
void loop() {
#if USE_MQTT
  netLoop();
#endif

  Reading r = measure();

  uint32_t now = millis();
  float dt_h = (now - lastEnergy_ms) / 3600000.0f;   // ms -> ώρες
  lastEnergy_ms = now;

  if (!r.ok) {
    logf("[!] Δεν ανιχνεύτηκε σήμα τάσης (timeout). Ελέγξτε ZMPT101B / GPIO2.\n");
    delay(1000);
    return;
  }

  energy_Wh += r.realPower * dt_h;

#if USE_MQTT
  // Καταμέτρηση κόστους με την τρέχουσα ΩΡΙΑΙΑ day-ahead τιμή. Οι ωριαίοι
  // και ημερήσιοι μετρητές μηδενίζονται στην αλλαγή ώρας / στα μεσάνυχτα
  // (τοπική ώρα Ελλάδας) και τυπώνεται το σύνολο που έκλεισε.
  if (timeSynced) {
    float dWh = r.realPower * dt_h;
    time_t nowT = time(nullptr);
    struct tm lt; localtime_r(&nowT, &lt);

    if (curYday >= 0 && (lt.tm_yday != curYday || lt.tm_year != curYear)) {
      logf("[day] Χθεσινη καταναλωση: %.3f kWh | κοστος: %.4f EUR\n",
           energyDay_Wh / 1000.0, costDay_EUR);
      energyDay_Wh = 0; costDay_EUR = 0; costHour_EUR = 0;
    }
    if (curHour >= 0 && lt.tm_hour != curHour && costHour_EUR > 0) {
      logf("[hour] Κοστος ωρας %02d:00 -> %.4f EUR\n", curHour, costHour_EUR);
      costHour_EUR = 0;
    }
    curHour = lt.tm_hour; curYday = lt.tm_yday; curYear = lt.tm_year;

    double dCost = dWh / 1000.0 * priceNowEURkWh();
    costHour_EUR += dCost;
    costDay_EUR  += dCost;
    energyDay_Wh += dWh;
  }
#endif

  // Χωρίς σήμα τάσης η μέτρηση ρεύματος δεν είναι αξιόπιστη (το παράθυρο
  // ορίζεται από τους μηδενισμούς της τάσης) -> κάνε ξεχωριστή μέτρηση.
  if (r.vrms <= 0.0f) currentOnlyReport(300);

#if WAVE_DUMP
  // Κάθε 20 s σύγκριση κυματομορφής ρεύματος με WiFi ON / OFF.
  static uint32_t lastWave = 0;
  if (lastWave == 0 || millis() - lastWave > 20000) {
    lastWave = millis();
    waveCompare();
  }
#endif

#if PRINT_DEBUG
  // Με φορτίο πάνω από 1 A, τρέξε σάρωση φάσης κάθε 10 δευτερόλεπτα.
  static uint32_t lastSweep = 0;
  if (r.irms > 1.0f && millis() - lastSweep > 10000) {
    lastSweep = millis();
    phaseSweep();
  }
#endif

#if PRINT_DEBUG
  // Crest factor = κορυφή / ενεργός τιμή. Καθαρό ημίτονο -> 1.41.
  // Πολύ μικρότερο σημαίνει ότι το σήμα "πλακώνει" (saturation του τελεστικού).
  float vrmsPin_mV = (VCAL > 0) ? (r.vrms / VCAL * 1000.0f) : 0.0f;
  float crest = (vrmsPin_mV > 1.0f) ? ((r.vmax - r.vmin) / 2.0f) / vrmsPin_mV : 0.0f;

  logf("[dbg] offsetV=%.0fmV offsetI=%.0fmV samples=%d | V: %d..%d mV ptp=%d CF=%.2f %s\n",
       offsetV, offsetI, r.samples, r.vmin, r.vmax, r.vmax - r.vmin, crest,
       // Το ταβάνι του ADC είναι ~2850 mV: αν το ακουμπάμε, κόβεται η κορυφή
       // ΑΝΕΞΑΡΤΗΤΑ από το τι δείχνει το crest factor.
       (r.vmax > 2800 || r.vmin < 150) ? "<<< ΚΟΡΥΦΗ ΣΤΟ ΤΑΒΑΝΙ - χαμηλωσε κι αλλο"
         : (crest > 1.33f && crest < 1.50f) ? "OK"
         : (crest > 0.0f ? "<<< σχημα ακομα στραβο" : ""));
#endif

  logf("V=%7.2f V | I=%6.3f A | P=%8.1f W | S=%8.1f VA | PF=%5.2f | E=%9.3f kWh\n",
                r.vrms, r.irms, r.realPower, r.apparentPower,
                r.powerFactor, energy_Wh / 1000.0);
#if USE_MQTT
  if (timeSynced)
    logf("      τιμη %7.4f EUR/kWh | ωρα %6.4f EUR | ημερα %6.4f EUR (%5.2f kWh)\n",
         priceNowEURkWh(), costHour_EUR, costDay_EUR, energyDay_Wh / 1000.0);
#endif

#if USE_MQTT
  if (millis() - lastPublish >= PUBLISH_EVERY_MS) {
    lastPublish = millis();
    publishState(r);
  }
#endif

  delay(200);
}
