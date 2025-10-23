import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

ADAPTER_PATH = "/org/bluez/hci0"

class Advertisement(dbus.service.Object):
    PATH_BASE = "/org/bluez/example/advertisement"

    def __init__(self, bus, index):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = "peripheral"
        self.service_uuids = ["180D"]  # Heart Rate example
        self.local_name = "Pi-BLE"
        self.include_tx_power = True
        self.connectable = False

        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        props = self.get_properties()[interface]
        return props[prop]

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return self.get_properties().get(interface, {})

    def get_properties(self):
        return {
            "org.bluez.LEAdvertisement1": {
                "Type": self.ad_type,
                "LocalName": self.local_name,
                "ServiceUUIDs": dbus.Array(self.service_uuids, signature="s"),
                "IncludeTxPower": dbus.Boolean(self.include_tx_power),
                "Connectable": dbus.Boolean(self.connectable),

            }
        }

    @dbus.service.method("org.freedesktop.DBus.Introspectable", in_signature="", out_signature="s")
    def Introspect(self):
        return ""

    @dbus.service.method("org.bluez.LEAdvertisement1", in_signature="", out_signature="")
    def Release(self):
        print("Advertisement released")


def register_advertisement(bus, adapter_path, advertisement):
    adapter = dbus.Interface(
        bus.get_object("org.bluez", adapter_path),
        "org.freedesktop.DBus.Properties",
    )
    adapter.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))

    ad_manager = dbus.Interface(
        bus.get_object("org.bluez", adapter_path),
        "org.bluez.LEAdvertisingManager1",
    )

    ad_manager.RegisterAdvertisement(
        advertisement.get_path(),
        {},
        reply_handler=lambda: print("✅ Quảng bá BLE thành công"),
        error_handler=lambda e: print("❌ Lỗi quảng bá:", e),
    )


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    ad = Advertisement(bus, 0)
    register_advertisement(bus, ADAPTER_PATH, ad)

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nDừng quảng bá")
        loop.quit()


if __name__ == "__main__":
    main()
