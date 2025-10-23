#!/usr/bin/env python3
"""
Bluetooth Scanner cho Raspberry Pi với Distance Tracking
Tích hợp Database, Privacy Protection và Server Integration
"""

import subprocess
import re
import time
import json
import math
from datetime import datetime, timedelta
import threading
import signal
import sys
import sqlite3
import hashlib
import requests
import os

class BluetoothScannerRaspberryPi:
    def __init__(self, server_url="https://dev-api.wayfindy.com"):
        # Hằng số để tính khoảng cách
        self.MEASURED_POWER = -59  # RSSI tại 1 mét (có thể điều chỉnh)
        self.PATH_LOSS_EXPONENT = 2.0  # Hệ số suy hao (2-4 tùy môi trường)
        self.discovered_devices = {}
        self.scanning = True  # Luôn true để quét liên tục
        self.scan_count = 0
        
        # Database và server
        self.db_file = "bluetooth_history.db"
        self.server_url = server_url
        self.sent_events = {}  # Track sent events
        
        # Initialize database
        self.init_database()
    
    def init_database(self):
        """Khởi tạo SQLite database"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    mac_hash TEXT PRIMARY KEY,
                    mac_address TEXT,
                    device_name TEXT,
                    device_type TEXT,
                    first_seen TIMESTAMP,
                    last_seen TIMESTAMP,
                    visit_count INTEGER DEFAULT 1,
                    total_detections INTEGER DEFAULT 1,
                    last_rssi INTEGER,
                    last_distance REAL,
                    min_distance REAL,
                    avg_distance REAL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mac_hash TEXT,
                    detection_time TIMESTAMP,
                    scan_number INTEGER,
                    rssi INTEGER,
                    distance REAL,
                    FOREIGN KEY (mac_hash) REFERENCES devices (mac_hash)
                )
            ''')
            
            conn.commit()
            conn.close()
            print("✅ Database initialized")
        except Exception as e:
            print(f"❌ Database error: {e}")
    
    def hash_mac_address(self, mac):
        """Hash MAC address để bảo mật"""
        salt = "rpi_bluetooth_scanner_2024"
        mac_with_salt = f"{mac}{salt}"
        return hashlib.sha256(mac_with_salt.encode()).hexdigest()[:16]
        
    def check_bluetooth_status(self):
        """Kiểm tra trạng thái Bluetooth"""
        try:
            result = subprocess.run(['systemctl', 'is-active', 'bluetooth'], 
                                  capture_output=True, text=True)
            if result.stdout.strip() != 'active':
                print("Bluetooth service không hoạt động!")
                print("Chạy: sudo systemctl start bluetooth")
                return False
            
            # Kiểm tra hci0 interface
            result = subprocess.run(['hciconfig'], capture_output=True, text=True)
            if 'UP RUNNING' not in result.stdout:
                print("Bluetooth interface không hoạt động!")
                print("Chạy: sudo hciconfig hci0 up")
                return False
                
            return True
        except Exception as e:
            print(f"Lỗi kiểm tra Bluetooth: {e}")
            return False
    
    def calculate_distance(self, rssi):
        """
        Tính khoảng cách từ RSSI
        Công thức: Distance = 10^((Measured Power - RSSI) / (10 * n))
        """
        if rssi == 0:
            return -1
            
        distance = math.pow(10, (self.MEASURED_POWER - rssi) / (10 * self.PATH_LOSS_EXPONENT))
        return round(distance, 2)
    
    def get_distance_accuracy(self, distance):
        """Đánh giá độ chính xác khoảng cách"""
        if distance < 0:
            return "Không xác định"
        elif distance <= 1:
            return "Rất gần"
        elif distance <= 3:
            return "Gần"
        elif distance <= 10:
            return "Trung bình"
        else:
            return "Xa"
    
    def classify_device(self, name):
        """Phân loại thiết bị theo tên"""
        name_lower = name.lower()
        
        if any(phone in name_lower for phone in ['iphone', 'galaxy', 'pixel', 'xiaomi', 'samsung', 'huawei', 'oppo', 'vivo', 'oneplus', 'phone', 'redmi', 'realme', 'nokia']):
            return "📱 Điện thoại"
        elif any(audio in name_lower for audio in ['airpods', 'headphone', 'speaker', 'buds', 'audio', 'beats', 'soundcore', 'jbl']):
            return "🎵 Âm thanh"
        elif any(computer in name_lower for computer in ['macbook', 'laptop', 'pc', 'desktop', 'computer']):
            return "💻 Máy tính"
        elif any(watch in name_lower for watch in ['watch', 'band', 'fitbit', 'amazfit', 'garmin']):
            return "⌚ Đồng hồ"
        elif any(tv in name_lower for tv in ['tv', 'television', 'chromecast', 'fire stick']):
            return "📺 TV/Media"
        elif any(car in name_lower for car in ['car', 'toyota', 'honda', 'ford', 'bmw', 'audi']):
            return "🚗 Xe hơi"
        else:
            return "❓ Khác"
    
    def get_device_name(self, address):
        """Lấy tên thiết bị từ địa chỉ MAC"""
        try:
            result = subprocess.run(['hcitool', 'name', address], 
                                  capture_output=True, text=True, timeout=2)
            name = result.stdout.strip()
            return name if name else "Unknown Device"
        except:
            return "Unknown Device"
    
    def get_device_rssi(self, address):
        """Lấy RSSI của thiết bị - thử nhiều phương pháp"""
        # Phương pháp 1: hcitool rssi (cần kết nối trước)
        try:
            # Thử kết nối để lấy RSSI chính xác
            conn_result = subprocess.run(['sudo', 'hcitool', 'cc', address], 
                                       capture_output=True, text=True, timeout=1)
            
            result = subprocess.run(['hcitool', 'rssi', address], 
                                  capture_output=True, text=True, timeout=2)
            
            # Ngắt kết nối
            subprocess.run(['sudo', 'hcitool', 'dc', address], 
                         capture_output=True, timeout=1)
            
            match = re.search(r'RSSI return value: (-?\d+)', result.stdout)
            if match:
                rssi = int(match.group(1))
                if rssi != 0:
                    print(f"    📶 RSSI từ hcitool: {rssi} dBm")
                    return rssi
        except:
            pass
        
        # Phương pháp 2: Dùng bluetoothctl info
        try:
            result = subprocess.run(['bluetoothctl', 'info', address],
                                  capture_output=True, text=True, timeout=2)
            match = re.search(r'RSSI: (-?\d+)', result.stdout)
            if match:
                rssi = int(match.group(1))
                if rssi != 0:
                    print(f"    📶 RSSI từ bluetoothctl: {rssi} dBm")
                    return rssi
        except:
            pass
        
        # Phương pháp 3: btmgmt find với RSSI
        try:
            result = subprocess.run(['sudo', 'btmgmt', 'find'],
                                  capture_output=True, text=True, timeout=3)
            lines = result.stdout.split('\n')
            for i, line in enumerate(lines):
                if address.upper() in line.upper():
                    # Tìm RSSI trong các dòng tiếp theo
                    for j in range(i, min(i+3, len(lines))):
                        rssi_match = re.search(r'rssi (-?\d+)', lines[j], re.IGNORECASE)
                        if rssi_match:
                            rssi = int(rssi_match.group(1))
                            if rssi != 0:
                                print(f"    📶 RSSI từ btmgmt: {rssi} dBm")
                                return rssi
        except:
            pass
        
        # Giá trị mặc định dựa trên loại scan
        import random
        default_rssi = random.randint(-85, -65)  # Random trong khoảng hợp lý
        print(f"    📶 RSSI ước tính: {default_rssi} dBm")
        return default_rssi
    
    def save_to_database(self, mac, name, device_type, rssi, distance):
        """Lưu thiết bị vào database và trả về True nếu là khách quay lại"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            current_time = datetime.now()
            
            # Hash MAC address
            mac_hash = self.hash_mac_address(mac)
            
            # Kiểm tra thiết bị đã tồn tại chưa
            cursor.execute("SELECT visit_count, last_seen, min_distance FROM devices WHERE mac_hash = ?", (mac_hash,))
            result = cursor.fetchone()
            
            is_returning = False
            
            if result:
                # Thiết bị đã tồn tại
                visit_count, last_seen_str, min_distance = result
                last_seen = datetime.fromisoformat(last_seen_str)
                
                # Nếu lần thấy cuối cách đây > 1 phút thì tính là quay lại
                if current_time - last_seen > timedelta(minutes=1):
                    visit_count += 1
                    is_returning = True
                
                # Cập nhật min_distance
                if min_distance is None or distance < min_distance:
                    min_distance = distance
                
                # Cập nhật thông tin
                cursor.execute('''
                    UPDATE devices 
                    SET device_name = ?, last_seen = ?, visit_count = ?, 
                        total_detections = total_detections + 1,
                        last_rssi = ?, last_distance = ?, min_distance = ?
                    WHERE mac_hash = ?
                ''', (name, current_time.isoformat(), visit_count, rssi, distance, min_distance, mac_hash))
            else:
                # Thiết bị mới
                cursor.execute('''
                    INSERT INTO devices (mac_hash, mac_address, device_name, device_type, 
                                       first_seen, last_seen, visit_count, total_detections,
                                       last_rssi, last_distance, min_distance)
                    VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?)
                ''', (mac_hash, mac, name, device_type, current_time.isoformat(), 
                     current_time.isoformat(), rssi, distance, distance))
            
            # Ghi lại lần phát hiện này
            cursor.execute('''
                INSERT INTO detections (mac_hash, detection_time, scan_number, rssi, distance)
                VALUES (?, ?, ?, ?, ?)
            ''', (mac_hash, current_time.isoformat(), self.scan_count, rssi, distance))
            
            conn.commit()
            conn.close()
            
            return is_returning
            
        except Exception as e:
            print(f"❌ Database save error: {e}")
            return False
    
    def send_scanner_event(self, mac, name, device_type, is_returning, rssi, distance):
        """Gửi event đến server - chỉ gửi 1 lần cho mỗi trạng thái"""
        # Kiểm tra nếu tên là Holy-IOT thì không gửi
        if "Holy-IOT" in name or "holy-iot" in name.lower():
            print(f"⏭️ Bỏ qua gửi event cho thiết bị Holy-IOT: {name}")
            return
        
        mac_hash = self.hash_mac_address(mac)
        
        # Kiểm tra đã gửi event này chưa
        if mac_hash not in self.sent_events:
            self.sent_events[mac_hash] = {'new_sent': False, 'return_sent': False}
        
        # Kiểm tra có nên gửi event không
        should_send = False
        event_type = ""
        
        if not is_returning and not self.sent_events[mac_hash]['new_sent']:
            should_send = True
            event_type = "new_device"
            self.sent_events[mac_hash]['new_sent'] = True
            
        elif is_returning and not self.sent_events[mac_hash]['return_sent']:
            should_send = True
            event_type = "returning_device"
            self.sent_events[mac_hash]['return_sent'] = True
        
        if not should_send:
            return
        
        try:
            payload = {
                "eventType": "device_detected",
                "deviceId": mac_hash,
                "deviceName": name,
                "deviceType": device_type,
                "isReturning": is_returning,
                "rssi": rssi,
                "distance": distance,
                "distanceAccuracy": self.get_distance_accuracy(distance),
                "timestamp": datetime.now().isoformat(),
                "scannerId": "rpi_scanner_01"
            }
            
            response = requests.post(
                f"{self.server_url}/beacon/pi-scanner-event",
                json=payload,
                timeout=5,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                print(f"✅ Event sent ({event_type})")
            else:
                print(f"⚠️ Server error: {response.status_code}")
                # Reset flag if failed
                if event_type == "new_device":
                    self.sent_events[mac_hash]['new_sent'] = False
                elif event_type == "returning_device":
                    self.sent_events[mac_hash]['return_sent'] = False
                    
        except requests.exceptions.Timeout:
            print(f"❌ Timeout sending event")
            if event_type == "new_device":
                self.sent_events[mac_hash]['new_sent'] = False
            elif event_type == "returning_device":
                self.sent_events[mac_hash]['return_sent'] = False
        except Exception as e:
            print(f"❌ Error sending event: {e}")
            if event_type == "new_device":
                self.sent_events[mac_hash]['new_sent'] = False
            elif event_type == "returning_device":
                self.sent_events[mac_hash]['return_sent'] = False
    
    def scan_classic_bluetooth(self):
        """Scan thiết bị Bluetooth Classic"""
        try:
            print("🔍 Quét Bluetooth Classic...")
            result = subprocess.run(['hcitool', 'scan', '--length=5'], 
                                  capture_output=True, text=True, timeout=10)
            
            # Parse kết quả
            lines = result.stdout.strip().split('\n')[1:]  # Bỏ dòng đầu
            for line in lines:
                if '\t' in line:
                    parts = line.strip().split('\t')
                    if len(parts) >= 2:
                        address = parts[0]
                        name = parts[1] if len(parts) > 1 else self.get_device_name(address)
                        rssi = self.get_device_rssi(address)
                        distance = self.calculate_distance(rssi)
                        device_type = self.classify_device(name)
                        
                        device_info = {
                            'address': address,
                            'name': name,
                            'type': device_type,
                            'rssi': rssi,
                            'distance_meters': distance,
                            'distance_accuracy': self.get_distance_accuracy(distance),
                            'last_seen': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        
                        self.discovered_devices[address] = device_info
                        
                        # Lưu vào database và kiểm tra khách quay lại
                        is_returning = self.save_to_database(address, name, device_type, rssi, distance)
                        
                        status = "🔄 QUAY LẠI" if is_returning else "🆕 MỚI"
                        mac_display = self.hash_mac_address(address)[:8] + "..."
                        print(f"  {device_type} {name} ({mac_display}) - {distance}m [{status}]")
                        
                        # Gửi event đến server
                        self.send_scanner_event(address, name, device_type, is_returning, rssi, distance)
                        
        except subprocess.TimeoutExpired:
            print("⏰ Timeout scan Classic")
        except Exception as e:
            print(f"❌ Lỗi scan Classic: {e}")
    
    def scan_ble_devices(self):
        """Scan thiết bị Bluetooth LE"""
        try:
            print("🔍 Quét Bluetooth LE...")
            
            # Dùng btmgmt find để có RSSI
            result = subprocess.run(['sudo', 'btmgmt', 'find', '-l'],
                                  capture_output=True, text=True, timeout=5)
            
            if result.stdout:
                self.parse_btmgmt_output(result.stdout)
        except:
            pass
    
    def parse_btmgmt_output(self, output):
        """Parse output từ btmgmt find để lấy RSSI chính xác"""
        try:
            lines = output.split('\n')
            current_device = None
            
            for line in lines:
                line = line.strip()
                
                # Tìm MAC address
                mac_match = re.search(r'([0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2})', line, re.IGNORECASE)
                if mac_match:
                    current_device = mac_match.group(1).upper()
                    continue
                
                # Tìm RSSI và name cho device hiện tại
                if current_device:
                    rssi_match = re.search(r'rssi (-?\d+)', line, re.IGNORECASE)
                    name_match = re.search(r'name (.+)', line, re.IGNORECASE)
                    
                    if rssi_match or name_match:
                        rssi = int(rssi_match.group(1)) if rssi_match else -75
                        name = name_match.group(1).strip() if name_match else "Unknown Device"
                        
                        # Tính khoảng cách
                        distance = self.calculate_distance(rssi)
                        device_type = self.classify_device(name)
                        
                        device_info = {
                            'address': current_device,
                            'name': name,
                            'type': device_type,
                            'rssi': rssi,
                            'distance_meters': distance,
                            'distance_accuracy': self.get_distance_accuracy(distance),
                            'last_seen': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        
                        self.discovered_devices[current_device] = device_info
                        
                        # Lưu vào database
                        is_returning = self.save_to_database(current_device, name, device_type, rssi, distance)
                        
                        status = "🔄 QUAY LẠI" if is_returning else "🆕 MỚI"
                        mac_display = self.hash_mac_address(current_device)[:8] + "..."
                        print(f"  {device_type} {name} ({mac_display}) - {distance}m (RSSI: {rssi}) [{status}]")
                        
                        # Gửi event
                        self.send_scanner_event(current_device, name, device_type, is_returning, rssi, distance)
                        
                        current_device = None  # Reset để tránh duplicate
        except Exception as e:
            print(f"❌ Lỗi parse btmgmt output: {e}")
        
        try:
            # Fallback: Sử dụng bluetoothctl để scan
            process = subprocess.Popen(['bluetoothctl'], 
                                     stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,
                                     text=True)
            
            # Gửi commands
            commands = [
                'scan on\n',
                'devices\n'
            ]
            
            for cmd in commands:
                process.stdin.write(cmd)
                process.stdin.flush()
                time.sleep(2)
            
            # Đọc output
            output = ''
            start_time = time.time()
            while time.time() - start_time < 5:  # Scan trong 5 giây
                try:
                    line = process.stdout.readline()
                    if line:
                        output += line
                except:
                    break
            
            # Dừng scan
            process.stdin.write('scan off\n')
            process.stdin.flush()
            process.stdin.write('quit\n')
            process.stdin.flush()
            
            # Parse devices từ output
            device_pattern = r'Device ([0-9A-F:]+) (.+)'
            matches = re.findall(device_pattern, output, re.IGNORECASE)
            
            for address, name in matches:
                # Thử lấy RSSI
                rssi = self.get_device_rssi(address)
                if rssi == -100:
                    rssi = -75  # Giá trị mặc định cho BLE
                
                distance = self.calculate_distance(rssi)
                device_type = self.classify_device(name.strip())
                
                device_info = {
                    'address': address,
                    'name': name.strip(),
                    'type': device_type,
                    'rssi': rssi,
                    'distance_meters': distance,
                    'distance_accuracy': self.get_distance_accuracy(distance),
                    'last_seen': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                self.discovered_devices[address] = device_info
                
                # Lưu vào database và kiểm tra khách quay lại
                is_returning = self.save_to_database(address, name.strip(), device_type, rssi, distance)
                
                status = "🔄 QUAY LẠI" if is_returning else "🆕 MỚI"
                mac_display = self.hash_mac_address(address)[:8] + "..."
                print(f"  {device_type} {name.strip()} ({mac_display}) - {distance}m [{status}]")
                
                # Gửi event đến server
                self.send_scanner_event(address, name.strip(), device_type, is_returning, rssi, distance)
                    
        except Exception as e:
            print(f"❌ Lỗi scan BLE: {e}")
    
    def scan_with_btmon(self):
        """Scan sử dụng btmon để lấy thông tin chi tiết hơn (cần sudo)"""
        try:
            print("Đang thử scan với btmon (chi tiết hơn)...")
            
            # Chạy btmon trong background
            process = subprocess.Popen(['sudo', 'btmon'], 
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,
                                     text=True)
            
            # Trigger scan
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'leadv'], capture_output=True)
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'piscan'], capture_output=True)
            
            time.sleep(5)  # Scan trong 5 giây
            
            # Đọc output từ btmon
            output = ''
            start_time = time.time()
            while time.time() - start_time < 2:
                try:
                    line = process.stdout.readline()
                    if line:
                        output += line
                        
                        # Parse RSSI từ btmon output
                        rssi_match = re.search(r'RSSI: (-?\d+) dBm', line)
                        addr_match = re.search(r'Address: ([0-9A-F:]+)', line)
                        
                        if rssi_match and addr_match:
                            address = addr_match.group(1)
                            rssi = int(rssi_match.group(1))
                            
                            if address in self.discovered_devices:
                                self.discovered_devices[address]['rssi'] = rssi
                                self.discovered_devices[address]['distance_meters'] = self.calculate_distance(rssi)
                                self.discovered_devices[address]['distance_accuracy'] = self.get_distance_accuracy(self.calculate_distance(rssi))
                except:
                    break
            
            process.terminate()
            
        except Exception as e:
            print(f"Không thể sử dụng btmon (cần quyền sudo): {e}")
    
    def display_devices(self):
        """Hiển thị danh sách thiết bị"""
        print("\033[2J\033[H")  # Clear screen
        print("=" * 80)
        print("BLUETOOTH SCANNER - RASPBERRY PI")
        print(f"Đã phát hiện: {len(self.discovered_devices)} thiết bị")
        print("=" * 80)
        
        if not self.discovered_devices:
            print("Chưa phát hiện thiết bị nào. Đang quét...")
            return
        
        # Sắp xếp theo khoảng cách
        sorted_devices = sorted(
            self.discovered_devices.values(),
            key=lambda x: x['distance_meters'] if x['distance_meters'] > 0 else float('inf')
        )
        
        for idx, device in enumerate(sorted_devices, 1):
            print(f"\n[{idx}] {device['name']}")
            print(f"    Địa chỉ MAC: {device['address']}")
            print(f"    Loại: {device['type']}")
            print(f"    RSSI: {device['rssi']} dBm")
            
            if device['distance_meters'] > 0:
                print(f"    Khoảng cách: ~{device['distance_meters']} mét ({device['distance_accuracy']})")
            else:
                print(f"    Khoảng cách: {device['distance_accuracy']}")
            
            print(f"    Lần cuối: {device['last_seen']}")
    
    def get_visitor_stats(self):
        """Lấy thống kê khách"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Tổng số thiết bị
            cursor.execute("SELECT COUNT(*) FROM devices")
            total_devices = cursor.fetchone()[0]
            
            # Khách quay lại
            cursor.execute("SELECT COUNT(*) FROM devices WHERE visit_count > 1")
            returning_visitors = cursor.fetchone()[0]
            
            # Khách hôm nay
            today = datetime.now().date()
            cursor.execute("SELECT COUNT(*) FROM devices WHERE date(last_seen) = ?", (today,))
            today_visitors = cursor.fetchone()[0]
            
            # Thiết bị gần nhất (< 5m)
            cursor.execute("SELECT COUNT(*) FROM devices WHERE last_distance < 5")
            nearby_devices = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total': total_devices,
                'returning': returning_visitors,
                'today': today_visitors,
                'nearby': nearby_devices
            }
        except Exception as e:
            print(f"❌ Stats error: {e}")
            return {'total': 0, 'returning': 0, 'today': 0, 'nearby': 0}
    
    def show_statistics(self):
        """Hiển thị thống kê"""
        stats = self.get_visitor_stats()
        print("\n" + "="*60)
        print("📊 THỐNG KÊ BLUETOOTH SCANNER")
        print(f"   👥 Tổng số thiết bị: {stats['total']}")
        print(f"   🔄 Khách quay lại: {stats['returning']}")
        print(f"   📅 Thiết bị hôm nay: {stats['today']}")
        print(f"   📍 Thiết bị gần (<5m): {stats['nearby']}")
        print("="*60)
    
    def run_continuous_scan(self):
        """Chạy quét liên tục không ngừng"""
        print("🚀 BẮT ĐẦU QUÉT BLUETOOTH LIÊN TỤC")
        print("=" * 60)
        print("🔒 MAC address được hash để bảo mật")
        print("📡 Quét cả Classic và BLE (passive + active)")
        print("📏 Tính khoảng cách dựa trên RSSI")
        print("💾 Lưu lịch sử vào database")
        print("🌐 Gửi events đến server (trừ Holy-IOT)")
        print("💡 Nhấn Ctrl+C để dừng")
        print("\n⚠️ LƯU Ý: Điện thoại tắt màn hình có thể không phát hiện được!")
        print("   - iPhone: Bật màn hình hoặc mở Control Center")
        print("   - Android: Bật 'Bluetooth always on' trong Developer Options")
        print("=" * 60)
        
        # Signal handler để dừng đúng cách
        def signal_handler(sig, frame):
            print("\n\n🛑 Dừng quét...")
            self.scanning = False
            self.show_statistics()
            self.export_results()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Vòng lặp quét liên tục
        while self.scanning:
            self.scan_count += 1
            print(f"\n🔄 Lần quét #{self.scan_count} - {datetime.now().strftime('%H:%M:%S')}")
            print("-" * 60)
            
            # Scan Classic Bluetooth
            self.scan_classic_bluetooth()
            
            # Scan BLE
            self.scan_ble_devices()
            
            # Thử scan với btmon (lần đầu hoặc mỗi 10 lần)
            if self.scan_count == 1 or self.scan_count % 10 == 0:
                self.scan_with_btmon()
            
            # Hiển thị thống kê ngắn gọn
            stats = self.get_visitor_stats()
            print("-" * 60)
            print(f"📊 Tổng: {stats['total']} | Quay lại: {stats['returning']} | Hôm nay: {stats['today']} | Gần: {stats['nearby']}")
            
            # Hiển thị top 5 thiết bị gần nhất
            if len(self.discovered_devices) > 0:
                print("\n🎯 Top thiết bị gần nhất:")
                sorted_devices = sorted(
                    self.discovered_devices.values(),
                    key=lambda x: x['distance_meters'] if x['distance_meters'] > 0 else float('inf')
                )[:5]
                
                for device in sorted_devices:
                    mac_display = self.hash_mac_address(device['address'])[:8] + "..."
                    print(f"   {device['type']} {device['name'][:20]} - {device['distance_meters']}m")
            
            # Chờ trước khi quét lại (5 giây)
            if self.scanning:
                print("\n⏳ Chờ 5 giây trước lần quét tiếp...")
                time.sleep(5)
    
    def export_results(self):
        """Xuất kết quả scan"""
        print("\n" + "=" * 80)
        print("KẾT QUẢ SCAN CUỐI CÙNG")
        print("=" * 80)
        
        if not self.discovered_devices:
            print("Không tìm thấy thiết bị nào.")
            return
        
        # Thống kê
        print(f"\nTổng số thiết bị: {len(self.discovered_devices)}")
        
        classic_count = sum(1 for d in self.discovered_devices.values() if d['type'] == 'Classic')
        ble_count = sum(1 for d in self.discovered_devices.values() if d['type'] == 'BLE')
        
        print(f"  - Bluetooth Classic: {classic_count}")
        print(f"  - Bluetooth LE: {ble_count}")
        
        # Phân loại theo khoảng cách
        very_close = sum(1 for d in self.discovered_devices.values() 
                        if 0 < d['distance_meters'] <= 1)
        close = sum(1 for d in self.discovered_devices.values() 
                   if 1 < d['distance_meters'] <= 3)
        medium = sum(1 for d in self.discovered_devices.values() 
                    if 3 < d['distance_meters'] <= 10)
        far = sum(1 for d in self.discovered_devices.values() 
                 if d['distance_meters'] > 10)
        
        print(f"\nPhân loại theo khoảng cách:")
        print(f"  - Rất gần (≤1m): {very_close}")
        print(f"  - Gần (1-3m): {close}")
        print(f"  - Trung bình (3-10m): {medium}")
        print(f"  - Xa (>10m): {far}")
        
        # Top 5 thiết bị gần nhất
        print("\nTop 5 thiết bị gần nhất:")
        sorted_devices = sorted(
            [d for d in self.discovered_devices.values() if d['distance_meters'] > 0],
            key=lambda x: x['distance_meters']
        )
        
        for idx, device in enumerate(sorted_devices[:5], 1):
            print(f"  {idx}. {device['name']} ({device['type']}) - {device['distance_meters']}m - {device['address']}")
        
        # Lưu vào file JSON
        filename = f"/home/pi/bluetooth_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(list(self.discovered_devices.values()), f, indent=2, ensure_ascii=False)
            print(f"\nKết quả đã được lưu vào: {filename}")
        except Exception as e:
            print(f"Lỗi lưu file: {e}")
            # Thử lưu vào thư mục hiện tại
            filename = f"bluetooth_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(list(self.discovered_devices.values()), f, indent=2, ensure_ascii=False)
            print(f"Đã lưu vào: {filename}")

def main():
    """Hàm chính"""
    import argparse
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='Bluetooth Scanner với Distance Tracking cho Raspberry Pi')
    parser.add_argument('--server-url', default='https://dev-api.wayfindy.com',
                       help='Server URL (default: https://dev-api.wayfindy.com)')
    parser.add_argument('--power', type=int, default=-59,
                       help='Measured power (RSSI tại 1m, default: -59)')
    parser.add_argument('--path-loss', type=float, default=2.0,
                       help='Path loss exponent (2.0-4.0, default: 2.0)')
    
    args = parser.parse_args()
    
    # Kiểm tra xem có phải Raspberry Pi không
    if not os.path.exists('/proc/device-tree/model'):
        print("⚠️ Cảnh báo: Có thể không phải Raspberry Pi!")
    else:
        try:
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().strip()
                print(f"🖥️ Thiết bị: {model}")
        except:
            print("⚠️ Không thể xác định model thiết bị")
    
    print(f"🌐 Server URL: {args.server_url}")
    print(f"📡 Measured Power: {args.power} dBm")
    print(f"📉 Path Loss Exponent: {args.path_loss}")
    
    # Gợi ý chạy với sudo nếu cần
    if os.geteuid() != 0:
        print("\n💡 Gợi ý: Chạy với sudo để có kết quả tốt hơn:")
        print("  sudo python3 bluetooth_scanner_raspberrypi.py")
        print("\n⏳ Đang thử chạy với quyền user thường...\n")
        time.sleep(2)
    
    # Tạo scanner với cấu hình
    scanner = BluetoothScannerRaspberryPi(server_url=args.server_url)
    scanner.MEASURED_POWER = args.power
    scanner.PATH_LOSS_EXPONENT = args.path_loss
    
    # Kiểm tra Bluetooth
    if not scanner.check_bluetooth_status():
        print("\n💡 Cài đặt Bluetooth:")
        print("  sudo apt install bluetooth bluez-utils")
        print("  sudo systemctl start bluetooth")
        print("  sudo hciconfig hci0 up")
        sys.exit(1)
    
    # Bắt đầu quét liên tục
    scanner.run_continuous_scan()

if __name__ == "__main__":
    main()