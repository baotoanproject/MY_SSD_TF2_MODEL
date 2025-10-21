[Unit]
Description=BLE Gatt Service
After=bluetooth.target

[Service]
ExecStart=/usr/bin/python3 /home/orangepi/new-ble-gatt.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
