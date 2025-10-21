Oct 21 05:53:48 orangepizero3 systemd[1]: Started ble-gatt.service - BLE Gatt Service.
Oct 21 05:54:00 orangepizero3 python3[647]: 2025-10-21 05:54:00,576 [ERROR] Cannot power on adapter: org.bluez.Error.Busy:
Oct 21 05:54:00 orangepizero3 python3[647]: Traceback (most recent call last):
Oct 21 05:54:00 orangepizero3 python3[647]:   File "/home/orangepi/new-ble-gatt.py", line 339, in power_on_adapter
Oct 21 05:54:00 orangepizero3 python3[647]:     props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))
Oct 21 05:54:00 orangepizero3 python3[647]:   File "/usr/lib/python3/dist-packages/dbus/proxies.py", line 141, in __call__
Oct 21 05:54:00 orangepizero3 python3[647]:     return self._connection.call_blocking(self._named_service,
Oct 21 05:54:00 orangepizero3 python3[647]:            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Oct 21 05:54:00 orangepizero3 python3[647]:   File "/usr/lib/python3/dist-packages/dbus/connection.py", line 634, in call_blocking
Oct 21 05:54:00 orangepizero3 python3[647]:     reply_message = self.send_message_with_reply_and_block(
Oct 21 05:54:00 orangepizero3 python3[647]:                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Oct 21 05:54:00 orangepizero3 python3[647]: dbus.exceptions.DBusException: org.bluez.Error.Busy:
Oct 21 05:54:00 orangepizero3 python3[647]: During handling of the above exception, another exception occurred:
Oct 21 05:54:00 orangepizero3 python3[647]: Traceback (most recent call last):
Oct 21 05:54:00 orangepizero3 python3[647]:   File "/home/orangepi/new-ble-gatt.py", line 404, in <module>
Oct 21 05:54:00 orangepizero3 python3[647]:     main()
Oct 21 05:54:00 orangepizero3 python3[647]:   File "/home/orangepi/new-ble-gatt.py", line 357, in main
Oct 21 05:54:00 orangepizero3 python3[647]:     power_on_adapter(bus)
Oct 21 05:54:00 orangepizero3 python3[647]:   File "/home/orangepi/new-ble-gatt.py", line 344, in power_on_adapter
Oct 21 05:54:00 orangepizero3 python3[647]:     props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))
Oct 21 05:54:00 orangepizero3 python3[647]:   File "/usr/lib/python3/dist-packages/dbus/proxies.py", line 141, in __call__
Oct 21 05:54:00 orangepizero3 python3[647]:     return self._connection.call_blocking(self._named_service,
Oct 21 05:54:00 orangepizero3 python3[647]:
