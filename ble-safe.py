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
# Global variable to track device that sent Wi-Fi command
# =========================
wifi_sender_device = None

# =========================
# Get Device from D-Bus Context (IMPROVED)
# =========================
def get_device_from_dbus_path(dbus_path):
    """Extract device info from D-Bus object path."""
    try:
        bus = dbus.SystemBus()

        # The D-Bus path contains device info
        # Format: /org/bluez/hci0/dev_XX_XX_XX_XX_XX_XX or similar
        path_parts = str(dbus_path).split('/')

        # Find device path in the object hierarchy
        for i, part in enumerate(path_parts):
            if part.startswith('dev_'):
                # Extract MAC from dev_XX_XX_XX_XX_XX_XX format
                mac_part = part[4:]  # Remove 'dev_' prefix
                mac_address = mac_part.replace('_', ':')

                # Get device object
                device_path = '/'.join(path_parts[:i+1])
                if device_path.startswith('/org/bluez'):
                    try:
                        device_obj = bus.get_object(BLUEZ, device_path)
                        device_props = dbus.Interface(device_obj, DBUS_PROP_IFACE)
                        props = device_props.GetAll("org.bluez.Device1")

                        return {
                            "address": props.get("Address", mac_address),
                            "name": props.get("Name", "Unknown"),
                            "path": device_path
                        }
                    except Exception as e:
                        logger.warning(f"Could not get device props for {device_path}: {e}")
                        return {
                            "address": mac_address,
                            "name": "Unknown",
                            "path": device_path
                        }

        logger.warning(f"Could not extract device info from path: {dbus_path}")
        return None

    except Exception as e:
        logger.error(f"Error extracting device from D-Bus path {dbus_path}: {e}")
        return None

def get_sending_device_from_message(message):
    """Get device info from the D-Bus message sender."""
    try:
        # Get the D-Bus connection that sent the message
        sender = message.get_sender()
        path = message.get_path()

        logger.debug(f"Message sender: {sender}, path: {path}")

        # Try to extract device info from the path
        device_info = get_device_from_dbus_path(path)
        if device_info:
            logger.info(f"📱 Identified sending device: {device_info['name']} ({device_info['address']})")
            return device_info

        # Fallback: scan for recently connected devices
        return get_most_recent_connected_device()

    except Exception as e:
        logger.error(f"Error identifying sending device: {e}")
        return get_most_recent_connected_device()

def get_most_recent_connected_device():
    """Get the most recently connected device as fallback."""
    try:
        bus = dbus.SystemBus()
        manager = dbus.Interface(
            bus.get_object(BLUEZ, "/"),
            DBUS_OM_IFACE
        )
        objects = manager.GetManagedObjects()

        connected_devices = []
        for path, interfaces in objects.items():
            if "org.bluez.Device1" in interfaces:
                device_props = interfaces["org.bluez.Device1"]

                # Check if device is connected
                if device_props.get("Connected", False):
                    device_address = device_props.get("Address", "")
                    device_name = device_props.get("Name", "Unknown")

                    connected_devices.append({
                        "address": device_address,
                        "name": device_name,
                        "path": path,
                        "connected_time": time.time()  # Approximate
                    })

        if connected_devices:
            # Return the last one (most recent)
            latest_device = connected_devices[-1]
            logger.info(f"🔍 Fallback to most recent connected device: {latest_device['name']} ({latest_device['address']})")
            return latest_device

        logger.warning("ℹ️ No connected BLE device found")
        return None

    except Exception as e:
        logger.error(f"❌ Error getting most recent connected device: {e}")
        return None

# =========================
# Bluetooth Remove Helper (SAME AS BEFORE)
# =========================
def try_remove_by_search(device_identifier):
    """Find and remove device by scanning all devices."""
    try:
        bus = dbus.SystemBus()
        adapter = dbus.Interface(
            bus.get_object(BLUEZ, ADAPTER_PATH),
            "org.bluez.Adapter1"
        )

        # Get all devices
        manager = dbus.Interface(
            bus.get_object(BLUEZ, "/"),
            DBUS_OM_IFACE
        )
        objects = manager.GetManagedObjects()

        for path, interfaces in objects.items():
            if "org.bluez.Device1" in interfaces:
                device_props = interfaces["org.bluez.Device1"]

                # Check Address (MAC) or path contains identifier
                device_address = device_props.get("Address", "")

                if (device_address.upper() == device_identifier.upper() or
                    device_identifier.replace("-", "_").upper() in str(path).upper()):

                    logger.info(f"🔍 Found device at path: {path}")
                    adapter.RemoveDevice(dbus.ObjectPath(path))
                    logger.info(f"✅ Removed device: {device_identifier}")
                    return True

        logger.warning(f"⚠️ Device not found: {device_identifier}")
        return False

    except Exception as e:
        logger.error(f"❌ Error searching device: {e}")
        return False

def remove_bluetooth_device(device_identifier):
    """Remove paired BLE device by MAC or UUID."""
    try:
        bus = dbus.SystemBus()
        adapter = dbus.Interface(
            bus.get_object(BLUEZ, ADAPTER_PATH),
            "org.bluez.Adapter1"
        )

        # Check format: UUID (iOS) or MAC (Android)
        if "-" in device_identifier and len(device_identifier) == 36:
            # iOS UUID format: 12345678-1234-5678-1234-123456789ABC
            dev_path = ADAPTER_PATH + "/dev_" + device_identifier.replace("-", "_")
        else:
            # Android MAC format: AA:BB:CC:DD:EE:FF
            dev_path = ADAPTER_PATH + "/dev_" + device_identifier.replace(":", "_")

        logger.info(f"🔍 Trying to remove device path: {dev_path}")
        adapter.RemoveDevice(dbus.ObjectPath(dev_path))
        logger.info(f"✅ Removed Bluetooth device: {device_identifier}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Cannot remove device {device_identifier}: {e}")
        # Try finding device by other method
        return try_remove_by_search(device_identifier)

def remove_wifi_sender_device():
    """Remove the device that sent Wi-Fi configuration command."""
    global wifi_sender_device

    if wifi_sender_device:
        success = remove_bluetooth_device(wifi_sender_device["address"])
        if success:
            logger.info(f"✅ Removed Wi-Fi sender device: {wifi_sender_device['name']} ({wifi_sender_device['address']})")
            wifi_sender_device = None
            return True
        else:
            logger.error(f"❌ Failed to remove Wi-Fi sender device: {wifi_sender_device['name']}")
            return False
    else:
        logger.warning("⚠️ No Wi-Fi sender device recorded to remove")
        return False

# =========================
# Advertisement (SAME AS BEFORE)
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
        self.connectable = True
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
# Base Characteristic (SAME AS BEFORE)
# =========================
class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = f"{service.path}/char{index}"
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
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
# Wi-Fi helpers (IMPROVED)
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

def connect_wifi(ssid, password, status_char=None, auto_remove_sender=False):
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

            # IMPROVED: Auto-remove only the device that sent Wi-Fi command
            if auto_remove_sender:
                logger.info("🔄 Auto-removing Wi-Fi sender device after successful connection...")
                time.sleep(2)  # Short delay before removal

                if remove_wifi_sender_device():
                    send("Sender removed")
                    logger.info("✅ Successfully removed Wi-Fi sender device")
                else:
                    send("Removal failed")
                    logger.warning("⚠️ Failed to remove Wi-Fi sender device")
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
# Characteristics (IMPROVED)
# =========================
class WifiStatusCharacteristic(Characteristic):
    @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    def __init__(self, bus, index, service):
        super().__init__(bus, index, STATUS_CHAR_UUID, ["notify"], service)
        self.notifying = False

    def send_status(self, status_str):
        if not self.notifying:
            return
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
        super().__init__(bus, index, WIFI_CHAR_UUID, ["write", "write-without-response"], service)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}", out_signature="")
    def WriteValue(self, value, options):
        global wifi_sender_device

        try:
            payload = bytes(value).decode("utf-8", errors="ignore")
            logger.info(f"Received command: {payload[:80]}...")

            # CRITICAL: Identify the device that sent this Wi-Fi command
            # Get message context to identify sender
            message = self._connection.get_message() if hasattr(self, '_connection') else None
            sender_device = get_sending_device_from_message(message) if message else get_most_recent_connected_device()

            # Store sender device info for Wi-Fi commands only
            if sender_device and (payload.strip().startswith("{") and "ssid" in payload.lower()):
                wifi_sender_device = sender_device
                logger.info(f"📱 Recorded Wi-Fi sender: {wifi_sender_device['name']} ({wifi_sender_device['address']})")

            # ---- Remove Wi-Fi sender device ----
            if payload.strip().lower() == "remove_sender":
                if remove_wifi_sender_device():
                    self.service.status_char.send_status("Wi-Fi sender removed")
                else:
                    self.service.status_char.send_status("No sender to remove")
                return

            # ---- Remove specific device command ----
            if payload.strip().lower().startswith("remove"):
                parts = payload.strip().split()
                if len(parts) == 2:
                    device_id = parts[1].strip()
                    success = remove_bluetooth_device(device_id)
                    if hasattr(self.service, "status_char"):
                        if success:
                            self.service.status_char.send_status(f"Removed {device_id}")
                        else:
                            self.service.status_char.send_status(f"Failed to remove {device_id}")
                else:
                    if hasattr(self.service, "status_char"):
                        self.service.status_char.send_status("Device ID required (remove AA:BB:CC:DD:EE:FF)")
                return

            # ---- JSON style commands (IMPROVED) ----
            if payload.strip().startswith("{"):
                data = json.loads(payload)

                # Remove specific device
                if "cmd" in data and data["cmd"].lower() == "remove":
                    device_id = data.get("mac", "")
                    if device_id:
                        logger.info(f"🔍 Removing specific device: {device_id}")
                        success = remove_bluetooth_device(device_id)
                        if success:
                            self.service.status_char.send_status(f"Removed {device_id}")
                        else:
                            self.service.status_char.send_status(f"Failed to remove {device_id}")
                    else:
                        self.service.status_char.send_status("Device ID required")
                    return

                # Remove Wi-Fi sender device
                if "cmd" in data and data["cmd"].lower() == "remove_sender":
                    if remove_wifi_sender_device():
                        self.service.status_char.send_status("Wi-Fi sender removed")
                    else:
                        self.service.status_char.send_status("No sender to remove")
                    return

                # Wi-Fi configuration with auto-remove sender option
                ssid = data.get("ssid", "").strip()
                password = data.get("password", "")
                auto_remove = data.get("auto_remove", True)  # Default to True for auto-remove sender

                if not ssid:
                    logger.error("SSID is required")
                    if hasattr(self.service, "status_char"):
                        self.service.status_char.send_status("SSID required")
                    return

                logger.info(f"📶 Wi-Fi config - SSID: {ssid}, Auto-remove sender: {auto_remove}")
                threading.Thread(
                    target=connect_wifi,
                    args=(ssid, password, self.service.status_char, auto_remove),
                    daemon=True
                ).start()
                return

            # ---- Disconnect command ----
            if payload.strip().lower() == "disconnect":
                logger.info("Received disconnect command - terminating BLE service")
                if hasattr(self.service, "status_char"):
                    self.service.status_char.send_status("Disconnecting")

                def delayed_shutdown():
                    time.sleep(0.5)
                    logger.info("Shutting down BLE service...")
                    import os
                    os._exit(0)

                threading.Thread(target=delayed_shutdown, daemon=True).start()
                return

            # ---- Legacy format (fallback) ----
            # Try to parse as JSON for backward compatibility
            try:
                data = json.loads(payload)
                ssid = data.get("ssid", "").strip()
                password = data.get("password", "")
                if not ssid:
                    logger.error("SSID is required")
                    if hasattr(self.service, "status_char"):
                        self.service.status_char.send_status("SSID required")
                    return

                # Default to auto-remove sender for legacy format
                threading.Thread(
                    target=connect_wifi,
                    args=(ssid, password, self.service.status_char, True),
                    daemon=True
                ).start()
            except json.JSONDecodeError:
                logger.error("Invalid command or JSON payload")
                if hasattr(self.service, "status_char"):
                    self.service.status_char.send_status("Invalid command")

        except Exception:
            logger.exception("Error processing command")
            if hasattr(self.service, "status_char"):
                self.service.status_char.send_status("Error")

# =========================
# Service & Application (SAME AS BEFORE)
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

    gatt_manager.RegisterApplication(
        app.get_path(),
        {},
        reply_handler=lambda: logger.info("✅ GATT application registered"),
        error_handler=lambda e: logger.error(f"❌ RegisterApplication error: {e}")
    )

    advert = Advertisement(bus, 0, [SERVICE_UUID])
    adv_manager.RegisterAdvertisement(
        advert.get_path(),
        {},
        reply_handler=lambda: logger.info("✅ Advertisement registered"),
        error_handler=lambda e: logger.error(f"❌ RegisterAdvertisement error: {e}")
    )

    logger.info('🚀 SAFE BLE Wi-Fi Configuration Service Ready!')
    logger.info('📱 Commands:')
    logger.info('   Wi-Fi: {"ssid":"YourSSID","password":"YourPass","auto_remove":true}')
    logger.info('   Remove specific: {"cmd":"remove","mac":"AA:BB:CC:DD:EE:FF"}')
    logger.info('   Remove sender: {"cmd":"remove_sender"}')
    logger.info('   Remove sender: "remove_sender"')
    logger.info('   Disconnect: "disconnect"')
    logger.info('')
    logger.info('🔒 SAFETY: Only the device that sends Wi-Fi command will be removed!')

    loop = GLib.MainLoop()

    def cleanup(*_):
        try:
            adv_manager.UnregisterAdvertisement(advert.get_path())
        except Exception:
            pass
        logger.info("Bye.")
        loop.quit()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    loop.run()

if __name__ == "__main__":
    main()
