#include "ble_companion.h"

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <Preferences.h>

static const char *kDeviceName = "VoxPin";
static const char *kServiceUuid = "a1a2a3a4-b1b2-c1c2-d1d2-e1e2e3e4e5e6";
static const char *kProfileUuid = "a1a2a3a4-b1b2-c1c2-d1d2-e1e2e3e4e5e7";
static const char *kDefaultProfile = "{\"name\":\"VoxPin\",\"language\":\"es\"}";

static Preferences prefs;
static BLECharacteristic *profile_char = nullptr;

class ProfileCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    String value = characteristic->getValue();
    if (value.isEmpty() || value.length() > 480) {
      return;
    }
    prefs.putString("profile", value);
  }
};

void ble_companion_begin(void)
{
  prefs.begin("voxpin", false);
  String profile = prefs.getString("profile", kDefaultProfile);
  if (profile.isEmpty()) {
    profile = kDefaultProfile;
  }

  BLEDevice::init(kDeviceName);
  BLEServer *server = BLEDevice::createServer();
  BLEService *service = server->createService(kServiceUuid);

  profile_char = service->createCharacteristic(
    kProfileUuid,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE
  );
  profile_char->setCallbacks(new ProfileCallbacks());
  profile_char->setValue(profile.c_str());
  service->start();

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(kServiceUuid);
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  BLEDevice::startAdvertising();
  Serial.println("Bluetooth: advertising as VoxPin");
}
