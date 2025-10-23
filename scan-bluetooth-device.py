#!/usr/bin/env python3
"""
Bluetooth Scanner đơn giản - Quét điện thoại gần đó
"""

import subprocess
import time
import json
import re
import signal
import sys
import sqlite3
import hashlib
import requests
from datetime import datetime, timedelta

class SimpleBluetoothScanner:
    def __init__(self, server_url="https://dev-api.wayfindy.com"):
        self.devices = {}
        self.running = True
        self.scan_count = 0
        self.db_file = "device_history.db"
        self.server_url = server_url
        self.sent_events = {}  # Track sent events: {mac_hash: {'new_sent': bool, 'return_sent': bool}}
        self.init_database()
        
    def init_database(self):
        """Khởi tạo SQLite database"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    mac_hash TEXT PRIMARY KEY,
                    device_name TEXT,
                    device_type TEXT,
                    first_seen TIMESTAMP,
                    last_seen TIMESTAMP,
                    visit_count INTEGER DEFAULT 1,
                    total_detections INTEGER DEFAULT 1
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mac_hash TEXT,
                    detection_time TIMESTAMP,
                    scan_number INTEGER,
                    FOREIGN KEY (mac_hash) REFERENCES devices (mac_hash)
                )
            ''')
            
            conn.commit()
            conn.close()
            print("✅ Database initialized")
        except Exception as e:
            print(f"❌ Database error: {e}")
    
    def signal_handler(self, sig, frame):
        print("\n🛑 Dừng quét...")
        self.running = False
        if self.devices:
            self.save_results()
        self.show_statistics()
        sys.exit(0)
    
    def check_bluetooth(self):
        """Kiểm tra Bluetooth"""
        try:
            result = subprocess.run(['hcitool', 'dev'], capture_output=True, text=True)
            if result.returncode == 0 and 'hci' in result.stdout:
                print("✅ Bluetooth sẵn sàng")
                return True
            else:
                print("❌ Không tìm thấy Bluetooth adapter")
                return False
        except:
            print("❌ Lỗi kiểm tra Bluetooth")
            return False
    
    def scan_nearby_devices(self):
        """Quét thiết bị bằng hcitool"""
        print("🔍 Đang quét thiết bị Bluetooth...")
        
        try:
            # Quét thiết bị
            result = subprocess.run(['hcitool', 'scan'], 
                                  capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                return self.parse_hcitool_output(result.stdout)
            else:
                print("❌ Lỗi khi quét")
                return []
        except subprocess.TimeoutExpired:
            print("⏰ Timeout khi quét")
            return []
        except Exception as e:
            print(f"❌ Lỗi: {e}")
            return []
    
    def parse_hcitool_output(self, output):
        """Parse kết quả từ hcitool scan"""
        devices = []
        lines = output.strip().split('\n')
        
        for line in lines[1:]:  # Bỏ dòng header
            line = line.strip()
            if line and '\t' in line:
                parts = line.split('\t', 1)
                if len(parts) == 2:
                    mac = parts[0].strip()
                    name = parts[1].strip() if parts[1].strip() else "Không có tên"
                    
                    device_type = self.classify_device(name)
                    
                    # Chỉ xử lý thiết bị điện thoại
                    if not device_type.startswith("📱"):
                        continue
                        
                    device = {
                        'mac': mac,
                        'name': name,
                        'type': device_type,
                        'time': datetime.now().strftime("%H:%M:%S"),
                        'scan_number': self.scan_count
                    }
                    
                    devices.append(device)
                    self.devices[mac] = device
                    
                    # Lưu vào database và kiểm tra khách quay lại
                    is_returning = self.save_to_database(mac, name, device['type'])
                    
                    status = "🔄 QUAY LẠI" if is_returning else "🆕 MỚI"
                    # Hiển thị MAC hash thay vì MAC thật để bảo mật
                    mac_display = self.hash_mac_address(mac)[:8] + "..."
                    print(f"📱 {name} ({mac_display}) - {device['type']} [{status}]")
                    
                    # Gửi event đến server
                    self.send_scanner_event(mac, name, device['type'], is_returning)
        
        return devices
    
    def classify_device(self, name):
        """Phân loại thiết bị"""
        name_lower = name.lower()
        
        if any(phone in name_lower for phone in ['iphone', 'galaxy', 'pixel', 'xiaomi', 'samsung', 'huawei', 'oppo', 'vivo', 'oneplus', 'phone']):
            return "📱 Điện thoại"
        elif any(audio in name_lower for audio in ['airpods', 'headphone', 'speaker', 'buds', 'audio', 'beats']):
            return "🎵 Âm thanh"
        elif any(computer in name_lower for computer in ['macbook', 'laptop', 'pc', 'desktop']):
            return "💻 Máy tính"
        elif any(watch in name_lower for watch in ['watch', 'band', 'fitbit']):
            return "⌚ Đồng hồ"
        else:
            return "❓ Khác"
    
    def hash_mac_address(self, mac):
        """Hash MAC address để bảo mật"""
        # Sử dụng SHA-256 với salt để hash MAC address
        salt = "bluetooth_scanner_2024"  # Có thể đổi salt này
        mac_with_salt = f"{mac}{salt}"
        return hashlib.sha256(mac_with_salt.encode()).hexdigest()[:16]
    
    def send_scanner_event(self, mac, name, device_type, is_returning):
        """Gửi event đến server - chỉ gửi 1 lần cho mỗi trạng thái"""
        mac_hash = self.hash_mac_address(mac)
        
        # Kiểm tra đã gửi event này chưa
        if mac_hash not in self.sent_events:
            self.sent_events[mac_hash] = {'new_sent': False, 'return_sent': False}
        
        # Kiểm tra có nên gửi event không
        should_send = False
        event_type = ""
        
        if not is_returning and not self.sent_events[mac_hash]['new_sent']:
            # Thiết bị mới lần đầu xuất hiện
            should_send = True
            event_type = "new_device"
            self.sent_events[mac_hash]['new_sent'] = True
            
        elif is_returning and not self.sent_events[mac_hash]['return_sent']:
            # Thiết bị quay lại lần đầu
            should_send = True  
            event_type = "returning_device"
            self.sent_events[mac_hash]['return_sent'] = True
        
        if not should_send:
            print(f"⏭️ Event already sent for {name} ({mac_hash[:8]}...) - skipping")
            return
        
        try:
            payload = {
                "eventType": "device_detected",
                "deviceId": mac_hash,
                "deviceName": name,
                "deviceType": device_type,
                "isReturning": is_returning,
                "timestamp": datetime.now().isoformat(),
                "scannerId": "pi_scanner_01"
            }
            
            response = requests.post(
                f"{self.server_url}/beacon/pi-scanner-event",
                json=payload,
                timeout=5,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                print(f"✅ Event sent to server ({event_type})")
            else:
                error_message = f"Server responded with status {response.status_code}"
                try:
                    error_detail = response.json().get('message', 'No error message')
                    error_message += f" - {error_detail}"
                except:
                    error_message += f" - Response: {response.text[:100]}..."
                print(f"⚠️ {error_message}")
                
        except requests.exceptions.Timeout as e:
            print(f"❌ Timeout error when sending event: Connection timeout after 5 seconds")
            # Reset flag nếu gửi thất bại
            if event_type == "new_device":
                self.sent_events[mac_hash]['new_sent'] = False
            elif event_type == "returning_device":
                self.sent_events[mac_hash]['return_sent'] = False
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Connection error when sending event: Cannot connect to server {self.server_url}")
            # Reset flag nếu gửi thất bại
            if event_type == "new_device":
                self.sent_events[mac_hash]['new_sent'] = False
            elif event_type == "returning_device":
                self.sent_events[mac_hash]['return_sent'] = False
        except requests.exceptions.RequestException as e:
            print(f"❌ HTTP request error when sending event: {str(e)}")
            # Reset flag nếu gửi thất bại
            if event_type == "new_device":
                self.sent_events[mac_hash]['new_sent'] = False
            elif event_type == "returning_device":
                self.sent_events[mac_hash]['return_sent'] = False
        except Exception as e:
            print(f"❌ Unexpected error when sending event: {str(e)} (Type: {type(e).__name__})")
            # Reset flag nếu có lỗi
            if event_type == "new_device":
                self.sent_events[mac_hash]['new_sent'] = False
            elif event_type == "returning_device":
                self.sent_events[mac_hash]['return_sent'] = False
    
    def save_to_database(self, mac, name, device_type):
        """Lưu thiết bị vào database và trả về True nếu là khách quay lại"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            current_time = datetime.now()
            
            # Hash MAC address để bảo mật
            mac_hash = self.hash_mac_address(mac)
            
            # Kiểm tra thiết bị đã tồn tại chưa
            cursor.execute("SELECT visit_count, last_seen FROM devices WHERE mac_hash = ?", (mac_hash,))
            result = cursor.fetchone()
            
            is_returning = False
            
            if result:
                # Thiết bị đã tồn tại
                visit_count, last_seen_str = result
                last_seen = datetime.fromisoformat(last_seen_str)
                
                # Nếu lần thấy cuối cách đây > 15 phút thì tính là quay lại
                if current_time - last_seen > timedelta(minutes=15):
                    visit_count += 1
                    is_returning = True
                
                # Cập nhật thông tin
                cursor.execute('''
                    UPDATE devices 
                    SET device_name = ?, last_seen = ?, visit_count = ?, total_detections = total_detections + 1
                    WHERE mac_hash = ?
                ''', (name, current_time.isoformat(), visit_count, mac_hash))
            else:
                # Thiết bị mới
                cursor.execute('''
                    INSERT INTO devices (mac_hash, device_name, device_type, first_seen, last_seen, visit_count, total_detections)
                    VALUES (?, ?, ?, ?, ?, 1, 1)
                ''', (mac_hash, name, device_type, current_time.isoformat(), current_time.isoformat()))
            
            # Ghi lại lần phát hiện này
            cursor.execute('''
                INSERT INTO detections (mac_hash, detection_time, scan_number)
                VALUES (?, ?, ?)
            ''', (mac_hash, current_time.isoformat(), self.scan_count))
            
            conn.commit()
            conn.close()
            
            return is_returning
            
        except Exception as e:
            print(f"❌ Database save error: {e}")
            return False
    
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
            
            conn.close()
            
            return {
                'total': total_devices,
                'returning': returning_visitors,
                'today': today_visitors
            }
        except Exception as e:
            print(f"❌ Stats error: {e}")
            return {'total': 0, 'returning': 0, 'today': 0}
    
    def show_statistics(self):
        """Hiển thị thống kê"""
        stats = self.get_visitor_stats()
        print("\n" + "="*50)
        print("📊 THỐNG KÊ KHÁCH")
        print(f"   👥 Tổng số thiết bị: {stats['total']}")
        print(f"   🔄 Khách quay lại: {stats['returning']}")
        print(f"   📅 Khách hôm nay: {stats['today']}")
        print("="*50)
    
    def save_results(self):
        """Lưu kết quả với MAC hash"""
        filename = f"bluetooth_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            # Tạo dữ liệu với MAC hash thay vì MAC thật
            safe_devices = {}
            for mac, device in self.devices.items():
                mac_hash = self.hash_mac_address(mac)
                safe_devices[mac_hash] = {
                    'name': device['name'],
                    'type': device['type'],
                    'time': device['time'],
                    'scan_number': device['scan_number']
                }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(safe_devices, f, ensure_ascii=False, indent=2)
            print(f"💾 Đã lưu {len(safe_devices)} thiết bị vào {filename}")
        except Exception as e:
            print(f"❌ Lỗi lưu file: {e}")
    
    def run_continuous_scan(self):
        """Chạy quét liên tục"""
        print("🚀 BẮT ĐẦU QUÉT BLUETOOTH")
        print("=" * 50)
        print("🔒 MAC address được hash để bảo mật")
        print("💡 Nhấn Ctrl+C để dừng")
        print("=" * 50)
        
        while self.running:
            self.scan_count += 1
            print(f"\n🔄 Lần quét #{self.scan_count} - {datetime.now().strftime('%H:%M:%S')}")
            
            devices_found = self.scan_nearby_devices()
            
            if devices_found:
                print(f"✅ Tìm thấy {len(devices_found)} thiết bị")
            else:
                print("⚪ Không tìm thấy thiết bị nào")
            
            # Hiển thị thống kê ngắn gọn
            stats = self.get_visitor_stats()
            print(f"📊 Tổng: {stats['total']} | Quay lại: {stats['returning']} | Hôm nay: {stats['today']}")
            
            # Chờ 5 giây trước lần quét tiếp theo
            try:
                print("⏳ Chờ 5 giây...")
                time.sleep(5)
            except KeyboardInterrupt:
                break

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Bluetooth Scanner với API integration')
    parser.add_argument('--server-url', default='https://dev-api.wayfindy.com',
                       help='Server URL (default: https://dev-api.wayfindy.com)')
    
    args = parser.parse_args()
    
    scanner = SimpleBluetoothScanner(server_url=args.server_url)
    
    print(f"🌐 Server URL: {args.server_url}")
    
    # Đăng ký signal handler
    signal.signal(signal.SIGINT, scanner.signal_handler)
    
    # Kiểm tra Bluetooth
    if not scanner.check_bluetooth():
        print("💡 Cài đặt: sudo apt install bluetooth bluez-utils")
        sys.exit(1)
    
    # Bắt đầu quét
    scanner.run_continuous_scan()

if __name__ == "__main__":
    main()