# Developer Guide

## Bước 0: Chuẩn bị Raspberry Pi

1. Tải Raspberry Pi Imager từ trang chính thức: https://www.raspberrypi.com/software
2. Ghi hệ điều hành:
   - Cắm thẻ nhớ microSD vào máy tính.

   - Mở Raspberry Pi Imager → Operating System → Use Custome → Chọn OS trong folder pi-os.

   - Chọn thiết bị lưu trữ (thẻ nhớ microSD).

   - Bấm Write để ghi hệ điều hành.

---

## Bước 1: Cài đặt các gói cần thiết

Copy file shell **install_dependencies.sh** trong folder `require-files` vào trong folder `/home/nets01/` trong Pi OS.
Chạy lệnh:
```
   cd /home/nets01/
   chmod +x install_dependencies.sh
   sudo ./install_dependencies.sh
```

---

## Bước 2: Cấu hình cho phép Bluetooth luôn bật khi khởi động, luôn cho phép các thiết bị khác tìm thấy và bỏ xác thực khi connect

1. Chạy lệnh: `sudo bluetoothctl`
2. Trong bluetooth terminal, nhập lần lượt như sau:
   ```
   power on
   discoverable on
   discoverable-timeout 0
   ```
   Sau khi nhập xong để thoát bluetooth terminal nhập: `exit`

3. Tiếp theo là cấu hình tự động bật discoverable khi khởi động:
   - Chạy lệnh: `sudo nano /etc/bluetooth/main.conf`
   - Tìm các dòng sau (nếu bị comment bằng `#` thì hãy bỏ đi, nếu chưa có thì hãy thêm vào):
     ```
     DiscoverableTimeout = 0
     PairableTimeout = 0
     ```

4. Cấu hình bỏ xác thực khi kết nối:
   - Vẫn ở trong file `main.conf`, bên dưới `[General]`, tìm hoặc thêm các dòng sau:
     ```
     ControllerMode=dual
     JustWorksRepairing=always
     ```

5. Tiếp theo copy file shell **bt-no-pair.sh** trong folder `require-files` vào trong folder `/usr/local/bin` trong Pi OS.
6. Chạy lệnh: `sudo chmod +x /usr/local/bin/bt-no-pair.sh`
7. Copy file **bt-no-pair.service** trong folder `pi-system-service-files` vào folder `/etc/systemd/system` trong Pi OS.
8. Chạy các lệnh bên dưới để kích hoạt:
   ```
   sudo systemctl daemon-reexec
   sudo systemctl daemon-reload
   sudo systemctl enable bt-no-pair.service
   ```

---

## Bước 3: Cấu hình và kích hoạt BLE Bluetooth Advertisement khi khởi động

1. Copy file **ble-advertise.py** trong folder `require-files` vào trong folder `/home/nets01/` trong Pi OS.
2. Copy file **ble-advertise.service** trong folder `pi-system-service-files` vào folder `/etc/systemd/system`.
3. Chạy các lệnh bên dưới để kích hoạt:
   ```
   sudo systemctl daemon-reexec
   sudo systemctl daemon-reload
   sudo systemctl enable ble-advertise.service
   ```

---

## Bước 4: Cấu hình và kích hoạt BLE GATT Server khi khởi động

**Mục đích**: Cho phép kết nối WiFi lấy từ thông tin App Wayfindy gửi qua và trả về trạng thái kết nối về App.

1. Copy file **ble-gatt.py** trong folder `require-files` vào trong folder `/home/nets01/` trong Pi OS.
2. Copy file **gatt.service** trong folder `pi-system-service-files` vào folder `/etc/systemd/system`.
3. Chạy các lệnh bên dưới để kích hoạt:
   ```
   sudo systemctl daemon-reexec
   sudo systemctl daemon-reload
   sudo systemctl enable gatt.service
   ```

---

## Bước 5: Cấu hình và kích hoạt HTTP Server để lấy Pi Serial khi khởi động

**Mục đích**: Lấy Pi Serial để lấy media file từ Wayfindy BE Server.

1. Copy file **get-serial-pi.py** trong folder `require-files` vào trong folder `/home/nets01/` trong Pi OS.
2. Copy file **serial_server.service** trong folder `pi-system-service-files` vào folder `/etc/systemd/system`.
3. Chạy các lệnh bên dưới để kích hoạt:
   ```
   sudo systemctl daemon-reexec
   sudo systemctl daemon-reload
   sudo systemctl enable serial_server.service
   ```

---

## Bước 6: Cấu hình chromium & kiosk mode

**Mục đích**: Khi khởi động Pi sẽ mở vào thẳng chromium ở chế độ kiok mode (toàn màn hình).

1. Copy file **chromium-kiosk.desktop** trong folder `require-files` vào folder `/etc/xdg/autostart/`.

---

## Hoàn tất

Sau khi hoàn thành tất cả các bước thì chạy lệnh:
```
sudo reboot
```
để khởi động lại Pi OS.

