[Unit]
Description=Disable Bluetooth Pairable
After=bluetooth.service
Requires=bluetooth.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/bt-no-pair.sh

[Install]
WantedBy=multi-user.target

#!/bin/bash
sleep 5
echo -e 'pairable off\ndiscoverable off\nquit' | bluetoothctl
