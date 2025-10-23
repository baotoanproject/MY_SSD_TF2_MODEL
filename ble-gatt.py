#!/usr/bin/env python3
import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib
import threading
import subprocess
import json
import logging
import time

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Constants
# -----------------------------
BLUEZ_SERVICE_NAME = 'org.bluez'
ADAPTER_PATH = '/org/bluez/hci0'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'

SERVICE_UUID = '12345678-1234-5678-1234-56789abcdef0'
WIFI_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef1'
STATUS_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef2'

DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'

# -----------------------------
# Base Characteristic
# -----------------------------
class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='ss', out_signature='v')
    def Get(self, interface, prop):
        if interface != GATT_CHRC_IFACE:
            raise dbus.exceptions.DBusException('Invalid interface')
        return self.get_properties()[GATT_CHRC_IFACE].get(prop)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise dbus.exceptions.DBusException('Invalid interface')
        return self.get_properties()[GATT_CHRC_IFACE]

# -----------------------------
# Wi-Fi Helpers
# -----------------------------
def wait_for_wifi_ready(timeout=15):
    for _ in range(timeout):
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE', 'device'],
                capture_output=True, text=True
            )
            lines = result.stdout.strip().split('\n')
            wifi_ready = any(l.split(':')[1] == 'wifi' and l.split(':')[2] in ('connected','disconnected','connecting') for l in lines)
            if wifi_ready:
                subprocess.run(['nmcli', 'device', 'wifi', 'rescan'], check=False)
                time.sleep(2)
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def wait_for_connection(ssid, timeout=20):
    for _ in range(timeout):
        result = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'],
                                capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            active, connected_ssid = line.split(':')
            if active == 'yes' and connected_ssid == ssid:
                return True
        time.sleep(1)
    return False

def connect_wifi(ssid, password, status_char=None):
    if status_char:
        status_char.send_status("Connecting...")
    if not wait_for_wifi_ready(timeout=15):
        logger.error("Wi-Fi interface not ready")
        if status_char:
            status_char.send_status("Interface not ready")
        return
    try:
        logger.info(f"Connecting to Wi-Fi SSID: {ssid}")
        subprocess.run(
            ['nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password],
            check=True, capture_output=True, text=True, timeout=30
        )
        if wait_for_connection(ssid):
            logger.info(f"Wi-Fi connected: {ssid}")
            if status_char:
                status_char.send_status("Connected")
        else:
            logger.error(f"Failed to connect to {ssid}")
            if status_char:
                status_char.send_status("Failed")
    except subprocess.CalledProcessError as e:
        logger.error(f"Wi-Fi connection failed: {e.stderr}")
        if status_char:
            status_char.send_status(f"Failed: {e.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("Wi-Fi connection timeout")
        if status_char:
            status_char.send_status("Timeout")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if status_char:
            status_char.send_status("Error")

# -----------------------------
# Wi-Fi Status Characteristic
# -----------------------------
class WifiStatusCharacteristic(Characteristic):
    @dbus.service.signal(DBUS_PROP_IFACE, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    def __init__(self, bus, index, service):
        super().__init__(bus, index, STATUS_CHAR_UUID, ['notify'], service)
        self.notifying = False

    def send_status(self, status_str):
        if not self.notifying:
            return
        value = [dbus.Byte(c.encode()) for c in status_str]
        self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": value}, [])

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='', out_signature='')
    def StartNotify(self):
        self.notifying = True

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='', out_signature='')
    def StopNotify(self):
        self.notifying = False

# -----------------------------
# Wi-Fi Config Characteristic
# -----------------------------
class WifiConfigCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        super().__init__(bus, index, WIFI_CHAR_UUID, ['write', 'write-without-response'], service)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}', out_signature='')
    def WriteValue(self, value, options):
        try:
            payload = ''.join([chr(byte) for byte in value])
            logger.info(f"Received Wi-Fi config: {payload[:50]}...")
            data = json.loads(payload)
            ssid = data.get("ssid")
            password = data.get("password")
            if not ssid:
                logger.error("SSID is required")
                return
            threading.Thread(
                target=connect_wifi,
                args=(ssid, password, self.service.status_char),
                daemon=True
            ).start()
        except Exception as e:
            logger.error(f"Error parsing Wi-Fi config: {e}")

# -----------------------------
# Wi-Fi Service
# -----------------------------
class WifiService(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/service'

    def __init__(self, bus, index):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = SERVICE_UUID
        self.primary = True
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

        self.config_char = WifiConfigCharacteristic(bus, 0, self)
        self.status_char = WifiStatusCharacteristic(bus, 1, self)
        self.add_characteristic(self.config_char)
        self.add_characteristic(self.status_char)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array([chrc.get_path() for chrc in self.characteristics], signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, chrc):
        self.characteristics.append(chrc)

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='ss', out_signature='v')
    def Get(self, interface, prop):
        if interface != GATT_SERVICE_IFACE:
            raise dbus.exceptions.DBusException('Invalid interface')
        return self.get_properties()[GATT_SERVICE_IFACE].get(prop)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise dbus.exceptions.DBusException('Invalid interface')
        return self.get_properties()[GATT_SERVICE_IFACE]

# -----------------------------
# Application
# -----------------------------
class Application(dbus.service.Object):
    PATH = '/org/bluez/example/app'

    def __init__(self, bus):
        self.path = self.PATH
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
        self.add_service(WifiService(bus, 0))

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.get_characteristics():
                response[chrc.get_path()] = chrc.get_properties()
        return response

# -----------------------------
# Main
# -----------------------------
def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    try:
        bus = dbus.SystemBus()
    except Exception as e:
        logger.error(f"Failed to get system bus: {e}")
        return

    app = Application(bus)

    try:
        gatt_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, ADAPTER_PATH), GATT_MANAGER_IFACE)
        gatt_manager.RegisterApplication(
            app.get_path(),
            {},
            reply_handler=lambda: logger.info("GATT application registered"),
            error_handler=lambda e: logger.error(f"Failed to register GATT application: {e}")
        )
        logger.info("BLE Wi-Fi server running. Send JSON: {\"ssid\":\"YourSSID\", \"password\":\"YourPass\"}")
        GLib.MainLoop().run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    main()
