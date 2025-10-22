⏺ Sửa file bt-no-pair.sh:

  #!/bin/bash
  sleep 5
  echo -e 'pairable off\ndiscoverable off\nquit' | bluetoothctl

  Quyền thực thi:
  sudo chmod +x /usr/local/bin/bt-no-pair.sh

⏺ Sửa file service (/etc/systemd/system/bt-no-pair.service):

  [Unit]
  Description=Disable Bluetooth Pairable
  After=bluetooth.service
  Requires=bluetooth.service

  [Service]
  Type=oneshot
  ExecStartPre=/bin/sleep 2
  ExecStart=/bin/bash /usr/local/bin/bt-no-pair.sh
  RemainAfterExit=yes
  StandardOutput=journal
  StandardError=journal

  [Install]
  WantedBy=multi-user.target

⏺ Reload và enable service:

  sudo systemctl daemon-reload
  sudo systemctl enable bt-no-pair.service
  sudo systemctl restart bt-no-pair.service
  sudo systemctl status bt-no-pair.service

  Debug nếu vẫn lỗi:
  sudo journalctl -u bt-no-pair.service -f
