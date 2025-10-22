#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib
import threading
import subprocess
import json
import logging
import time
import signal
import sys

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("ble-wifi-server")

# =========================
# BlueZ / D-Bus Const
# =========================
BLUEZ = "org.bluez"
ADAPTER_PATH = "/org/bluez/hci0"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"

# =========================
# Your Service/Char UUIDs
# =========================
SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
WIFI_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
STATUS_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef2"

LOCAL_NAME = "orangepi-1"
ADVERT_PATH_BASE = "/org/bluez/example/advertisement"
APP_PATH = "/org/bluez/example/app"
SERVICE_PATH_BASE = "/org/bluez/example/service"

# =========================
# Advertisement
# =========================
class Advertisement(dbus.service.Object):
    IFACE = "org.bluez.LEAdvertisement1"

    def __init__(self, bus, index, service_uuids):
        self.path = f"{ADVERT_PATH_BASE}{index}"
        self.bus = bus
        self.ad_type = "peripheral"
        self.service_uuids = service_uuids
        self.local_name = LOCAL_NAME
        self.include_tx_power = True
        self.connectable = True  # Cho phép connect GATT, KHÔNG yêu cầu bonding
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            self.IFACE: {
                "Type": self.ad_type,
                "LocalName": self.local_name,
                "ServiceUUIDs": dbus.Array(self.service_uuids, signature="s"),
                "IncludeTxPower": dbus.Boolean(self.include_tx_power),
                "Connectable": dbus.Boolean(self.connectable),
                # Không thêm bất kỳ trường security nào → tránh pairing
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        props = self.get_properties()[interface]
        return props[prop]

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return self.get_properties().get(interface, {})

    @dbus.service.method("org.freedesktop.DBus.Introspectable", in_signature="", out_signature="s")
    def Introspect(self):
        return ""

    @dbus.service.method(IFACE, in_signature="", out_signature="")
    def Release(self):
        logger.info("Advertisement released")

# =========================
# Base Characteristic
# =========================
class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = f"{service.path}/char{index}"
        self.bus = bus
        self.uuid = uuid
        self.flags = flags  # KHÔNG dùng encrypt-*/secure-* để tránh pairing
        self.service = service
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags,
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        return self.get_properties()[GATT_CHRC_IFACE].get(prop)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return self.get_properties()[GATT_CHRC_IFACE]

# =========================
# Wi-Fi helpers
# =========================
def wait_for_wifi_ready(timeout=15):
    for _ in range(timeout):
        try:
            r = subprocess.run(
                ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"],
                capture_output=True, text=True, check=False
            )
            lines = [l for l in r.stdout.strip().split("\n") if l]
            wifi_ready = any(
                (parts := l.split(":")) and len(parts) >= 3 and parts[1] == "wifi" and parts[2] in ("connected", "disconnected", "connecting")
                for l in lines
            )
            if wifi_ready:
                subprocess.run(["nmcli", "device", "wifi", "rescan"], check=False)
                time.sleep(2)
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def wait_for_connection(ssid, timeout=25):
    for _ in range(timeout):
        r = subprocess.run(
            ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
            capture_output=True, text=True, check=False
        )
        for line in r.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(":")
            if len(parts) >= 2 and parts[0] == "yes" and parts[1] == ssid:
                return True
        time.sleep(1)
    return False

def connect_wifi(ssid, password, status_char=None):
    def send(msg):
        if status_char:
            status_char.send_status(msg)

    send("Connecting...")
    if not wait_for_wifi_ready(timeout=15):
        logger.error("Wi-Fi interface not ready")
        send("Interface not ready")
        return

    try:
        logger.info(f"Connecting to SSID: {ssid}")
        args = ["nmcli", "dev", "wifi", "connect", ssid]
        if password:
            args += ["password", password]
        subprocess.run(args, capture_output=True, text=True, timeout=35, check=True)

        if wait_for_connection(ssid):
            logger.info(f"Wi-Fi connected: {ssid}")
            send("Connected")
        else:
            logger.error(f"Failed to connect to {ssid}")
            send("Failed")
    except subprocess.CalledProcessError as e:
        logger.error(f"nmcli failed: {e.stderr}")
        send(f"Failed: {e.stderr.strip()[:80]}")
    except subprocess.TimeoutExpired:
        logger.error("Wi-Fi connection timeout")
        send("Timeout")
    except Exception as e:
        logger.exception("Unexpected error")
        send("Error")

# =========================
# Characteristics
# =========================
class WifiStatusCharacteristic(Characteristic):
    @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    def __init__(self, bus, index, service):
        # Chỉ notify → không yêu cầu mã hóa
        super().__init__(bus, index, STATUS_CHAR_UUID, ["notify"], service)
        self.notifying = False

    def send_status(self, status_str):
        if not self.notifying:
            return
        # String -> array of bytes
        value = [dbus.Byte(b) for b in status_str.encode("utf-8")]
        self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": value}, [])

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="", out_signature="")
    def StartNotify(self):
        self.notifying = True

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="", out_signature="")
    def StopNotify(self):
        self.notifying = False

class WifiConfigCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        # write / write-without-response → không yêu cầu pairing
        super().__init__(bus, index, WIFI_CHAR_UUID, ["write", "write-without-response"], service)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}", out_signature="")
    def WriteValue(self, value, options):
        try:
            payload = bytes(value).decode("utf-8", errors="ignore")
            logger.info(f"Received Wi-Fi config: {payload[:80]}...")
			# Check if it's a disconnect command
            if payload.strip().lower() == "disconnect":
                logger.info("Received disconnect command - terminating BLE service")
                # Send acknowledgment
                if hasattr(self.service, "status_char"):
                    self.service.status_char.send_status("Disconnecting")

                # Schedule shutdown after a brief delay
                def delayed_shutdown():
                    time.sleep(0.5)  # Give time for status to be sent
                    logger.info("Shutting down BLE service...")
                    import os
                    os._exit(0)  # Force exit the process

                threading.Thread(target=delayed_shutdown, daemon=True).start()
                return
            data = json.loads(payload)
            ssid = data.get("ssid", "").strip()
            password = data.get("password", "")
            if not ssid:
                logger.error("SSID is required")
                if hasattr(self.service, "status_char"):
                    self.service.status_char.send_status("SSID required")
                return

            threading.Thread(
                target=connect_wifi,
                args=(ssid, password, self.service.status_char),
                daemon=True
            ).start()
        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            if hasattr(self.service, "status_char"):
                self.service.status_char.send_status("Invalid JSON")
        except Exception as e:
            logger.exception("Error parsing Wi-Fi config")
            if hasattr(self.service, "status_char"):
                self.service.status_char.send_status("Error")

# =========================
# Service & Application
# =========================
class WifiService(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = f"{SERVICE_PATH_BASE}{index}"
        self.bus = bus
        self.uuid = SERVICE_UUID
        self.primary = True
        self.characteristics = []
        super().__init__(bus, self.path)

        self.config_char = WifiConfigCharacteristic(bus, 0, self)
        self.status_char = WifiStatusCharacteristic(bus, 1, self)

        self.add_characteristic(self.config_char)
        self.add_characteristic(self.status_char)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, chrc):
        self.characteristics.append(chrc)

    def get_characteristics(self):
        return self.characteristics

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": dbus.Array(
                    [c.get_path() for c in self.characteristics], signature="o"
                ),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        return self.get_properties()[GATT_SERVICE_IFACE].get(prop)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return self.get_properties()[GATT_SERVICE_IFACE]

class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = APP_PATH
        self.services = []
        super().__init__(bus, self.path)
        self.add_service(WifiService(bus, 0))

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.get_characteristics():
                response[chrc.get_path()] = chrc.get_properties()
        return response

# =========================
# Main
# =========================
def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    app = Application(bus)
    gatt_manager = dbus.Interface(bus.get_object(BLUEZ, ADAPTER_PATH), GATT_MANAGER_IFACE)
    adv_manager = dbus.Interface(bus.get_object(BLUEZ, ADAPTER_PATH), LE_ADV_MANAGER_IFACE)

    # Register GATT
    gatt_manager.RegisterApplication(
        app.get_path(),
        {},
        reply_handler=lambda: logger.info("✅ GATT application registered"),
        error_handler=lambda e: logger.error(f"❌ RegisterApplication error: {e}")
    )

    # Register Advertisement
    advert = Advertisement(bus, 0, [SERVICE_UUID])
    adv_manager.RegisterAdvertisement(
        advert.get_path(),
        {},
        reply_handler=lambda: logger.info("✅ Advertisement registered"),
        error_handler=lambda e: logger.error(f"❌ RegisterAdvertisement error: {e}")
    )

    logger.info('🚀 Ready. Write JSON to WIFI_CHAR: {"ssid":"YourSSID","password":"YourPass"}')
    logger.info("🔔 Subscribe STATUS_CHAR (notify) để nhận trạng thái: Connecting/Connected/Failed...")

    loop = GLib.MainLoop()

    def cleanup(*_):
        try:
            adv_manager.UnregisterAdvertisement(advert.get_path())
        except Exception:
            pass
        try:
            advert.RemoveFromConnection = True  # no-op marker
        except Exception:
            pass
        logger.info("Bye.")
        loop.quit()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    loop.run()

if __name__ == "__main__":
    # Yêu cầu: sudo, bluez + bluetoothd đang chạy (có thể cần -E cho LE peripheral)
    main()
