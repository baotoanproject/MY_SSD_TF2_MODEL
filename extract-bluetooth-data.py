#!/usr/bin/env python3
"""
Script trích xuất dữ liệu từ SQLite database của Bluetooth Scanner
"""

import sqlite3
import json
import argparse
from datetime import datetime, timedelta
import csv

class BluetoothDataExtractor:
    def __init__(self, db_file="device_history.db"):
        self.db_file = db_file
        
    def connect_db(self):
        """Kết nối đến database"""
        try:
            return sqlite3.connect(self.db_file)
        except Exception as e:
            print(f"❌ Lỗi kết nối database: {e}")
            return None
    
    def get_all_devices(self):
        """Lấy tất cả thiết bị từ database"""
        conn = self.connect_db()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT mac_hash, device_name, device_type, first_seen, last_seen, 
                       visit_count, total_detections
                FROM devices
                ORDER BY last_seen DESC
            ''')
            
            devices = []
            for row in cursor.fetchall():
                devices.append({
                    'mac_hash': row[0],
                    'device_name': row[1],
                    'device_type': row[2],
                    'first_seen': row[3],
                    'last_seen': row[4],
                    'visit_count': row[5],
                    'total_detections': row[6]
                })
            
            conn.close()
            return devices
            
        except Exception as e:
            print(f"❌ Lỗi truy vấn: {e}")
            conn.close()
            return []
    
    def get_devices_by_date(self, date_str):
        """Lấy thiết bị theo ngày cụ thể (format: YYYY-MM-DD)"""
        conn = self.connect_db()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT mac_hash, device_name, device_type, first_seen, last_seen, 
                       visit_count, total_detections
                FROM devices
                WHERE date(last_seen) = ?
                ORDER BY last_seen DESC
            ''', (date_str,))
            
            devices = []
            for row in cursor.fetchall():
                devices.append({
                    'mac_hash': row[0],
                    'device_name': row[1],
                    'device_type': row[2],
                    'first_seen': row[3],
                    'last_seen': row[4],
                    'visit_count': row[5],
                    'total_detections': row[6]
                })
            
            conn.close()
            return devices
            
        except Exception as e:
            print(f"❌ Lỗi truy vấn: {e}")
            conn.close()
            return []
    
    def get_returning_visitors(self):
        """Lấy danh sách khách quay lại (visit_count > 1)"""
        conn = self.connect_db()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT mac_hash, device_name, device_type, first_seen, last_seen, 
                       visit_count, total_detections
                FROM devices
                WHERE visit_count > 1
                ORDER BY visit_count DESC
            ''')
            
            devices = []
            for row in cursor.fetchall():
                devices.append({
                    'mac_hash': row[0],
                    'device_name': row[1],
                    'device_type': row[2],
                    'first_seen': row[3],
                    'last_seen': row[4],
                    'visit_count': row[5],
                    'total_detections': row[6]
                })
            
            conn.close()
            return devices
            
        except Exception as e:
            print(f"❌ Lỗi truy vấn: {e}")
            conn.close()
            return []
    
    def get_device_detections(self, mac_hash):
        """Lấy lịch sử phát hiện của một thiết bị cụ thể"""
        conn = self.connect_db()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT detection_time, scan_number
                FROM detections
                WHERE mac_hash = ?
                ORDER BY detection_time DESC
            ''', (mac_hash,))
            
            detections = []
            for row in cursor.fetchall():
                detections.append({
                    'detection_time': row[0],
                    'scan_number': row[1]
                })
            
            conn.close()
            return detections
            
        except Exception as e:
            print(f"❌ Lỗi truy vấn: {e}")
            conn.close()
            return []
    
    def get_statistics(self):
        """Lấy thống kê tổng quan"""
        conn = self.connect_db()
        if not conn:
            return {}
        
        try:
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
            
            # Khách 7 ngày qua
            week_ago = (datetime.now() - timedelta(days=7)).date()
            cursor.execute("SELECT COUNT(*) FROM devices WHERE date(last_seen) >= ?", (week_ago,))
            week_visitors = cursor.fetchone()[0]
            
            # Thiết bị theo loại
            cursor.execute('''
                SELECT device_type, COUNT(*) 
                FROM devices 
                GROUP BY device_type
            ''')
            device_types = dict(cursor.fetchall())
            
            # Tổng số lần phát hiện
            cursor.execute("SELECT COUNT(*) FROM detections")
            total_detections = cursor.fetchone()[0]
            
            # Thiết bị phổ biến nhất (nhiều lần ghé thăm nhất)
            cursor.execute('''
                SELECT device_name, visit_count 
                FROM devices 
                ORDER BY visit_count DESC 
                LIMIT 5
            ''')
            top_devices = cursor.fetchall()
            
            conn.close()
            
            return {
                'total_devices': total_devices,
                'returning_visitors': returning_visitors,
                'today_visitors': today_visitors,
                'week_visitors': week_visitors,
                'device_types': device_types,
                'total_detections': total_detections,
                'top_devices': top_devices
            }
            
        except Exception as e:
            print(f"❌ Lỗi thống kê: {e}")
            conn.close()
            return {}
    
    def export_to_json(self, data, filename):
        """Xuất dữ liệu ra file JSON"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ Đã xuất dữ liệu ra {filename}")
        except Exception as e:
            print(f"❌ Lỗi xuất JSON: {e}")
    
    def export_to_csv(self, devices, filename):
        """Xuất dữ liệu ra file CSV"""
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                if devices:
                    writer = csv.DictWriter(f, fieldnames=devices[0].keys())
                    writer.writeheader()
                    writer.writerows(devices)
                print(f"✅ Đã xuất dữ liệu ra {filename}")
        except Exception as e:
            print(f"❌ Lỗi xuất CSV: {e}")
    
    def print_statistics(self):
        """In thống kê ra màn hình"""
        stats = self.get_statistics()
        
        if not stats:
            print("❌ Không thể lấy thống kê")
            return
        
        print("\n" + "="*60)
        print("📊 THỐNG KÊ BLUETOOTH SCANNER")
        print("="*60)
        print(f"👥 Tổng số thiết bị: {stats.get('total_devices', 0)}")
        print(f"🔄 Khách quay lại: {stats.get('returning_visitors', 0)}")
        print(f"📅 Khách hôm nay: {stats.get('today_visitors', 0)}")
        print(f"📆 Khách 7 ngày qua: {stats.get('week_visitors', 0)}")
        print(f"📡 Tổng lần phát hiện: {stats.get('total_detections', 0)}")
        
        print("\n📱 PHÂN LOẠI THIẾT BỊ:")
        for device_type, count in stats.get('device_types', {}).items():
            print(f"   {device_type}: {count}")
        
        print("\n🏆 TOP 5 THIẾT BỊ GHÉ THĂM NHIỀU NHẤT:")
        for i, (name, visits) in enumerate(stats.get('top_devices', []), 1):
            print(f"   {i}. {name}: {visits} lần")
        
        print("="*60)
    
    def print_devices_table(self, devices, limit=None):
        """In bảng thiết bị"""
        if not devices:
            print("Không có thiết bị nào")
            return
        
        if limit:
            devices = devices[:limit]
        
        print("\n" + "="*100)
        print(f"{'MAC Hash':<20} {'Tên thiết bị':<30} {'Loại':<15} {'Lần ghé':<10} {'Lần thấy cuối':<20}")
        print("="*100)
        
        for device in devices:
            mac_display = device['mac_hash'][:8] + "..."
            name_display = device['device_name'][:28] if len(device['device_name']) > 28 else device['device_name']
            last_seen = datetime.fromisoformat(device['last_seen']).strftime("%Y-%m-%d %H:%M")
            
            print(f"{mac_display:<20} {name_display:<30} {device['device_type']:<15} "
                  f"{device['visit_count']:<10} {last_seen:<20}")
        
        print("="*100)
        print(f"Hiển thị {len(devices)} thiết bị")

def main():
    parser = argparse.ArgumentParser(description='Trích xuất dữ liệu Bluetooth Scanner từ SQLite')
    parser.add_argument('--db', default='device_history.db', help='Đường dẫn database SQLite')
    parser.add_argument('--command', choices=['all', 'today', 'date', 'returning', 'stats', 'device'],
                       default='stats', help='Lệnh trích xuất')
    parser.add_argument('--date', help='Ngày cụ thể (YYYY-MM-DD) cho lệnh date')
    parser.add_argument('--mac', help='MAC hash cho lệnh device')
    parser.add_argument('--export-json', help='Xuất kết quả ra file JSON')
    parser.add_argument('--export-csv', help='Xuất kết quả ra file CSV')
    parser.add_argument('--limit', type=int, help='Giới hạn số lượng kết quả hiển thị')
    
    args = parser.parse_args()
    
    extractor = BluetoothDataExtractor(args.db)
    
    # Xử lý các lệnh
    if args.command == 'stats':
        extractor.print_statistics()
        
    elif args.command == 'all':
        devices = extractor.get_all_devices()
        print(f"\n📱 TẤT CẢ THIẾT BỊ ({len(devices)} thiết bị)")
        extractor.print_devices_table(devices, args.limit)
        
        if args.export_json:
            extractor.export_to_json(devices, args.export_json)
        if args.export_csv:
            extractor.export_to_csv(devices, args.export_csv)
    
    elif args.command == 'today':
        today = datetime.now().strftime('%Y-%m-%d')
        devices = extractor.get_devices_by_date(today)
        print(f"\n📅 THIẾT BỊ HÔM NAY ({len(devices)} thiết bị)")
        extractor.print_devices_table(devices, args.limit)
        
        if args.export_json:
            extractor.export_to_json(devices, args.export_json)
        if args.export_csv:
            extractor.export_to_csv(devices, args.export_csv)
    
    elif args.command == 'date':
        if not args.date:
            print("❌ Cần chỉ định ngày với --date YYYY-MM-DD")
            return
        
        devices = extractor.get_devices_by_date(args.date)
        print(f"\n📅 THIẾT BỊ NGÀY {args.date} ({len(devices)} thiết bị)")
        extractor.print_devices_table(devices, args.limit)
        
        if args.export_json:
            extractor.export_to_json(devices, args.export_json)
        if args.export_csv:
            extractor.export_to_csv(devices, args.export_csv)
    
    elif args.command == 'returning':
        devices = extractor.get_returning_visitors()
        print(f"\n🔄 KHÁCH QUAY LẠI ({len(devices)} thiết bị)")
        extractor.print_devices_table(devices, args.limit)
        
        if args.export_json:
            extractor.export_to_json(devices, args.export_json)
        if args.export_csv:
            extractor.export_to_csv(devices, args.export_csv)
    
    elif args.command == 'device':
        if not args.mac:
            print("❌ Cần chỉ định MAC hash với --mac")
            return
        
        detections = extractor.get_device_detections(args.mac)
        print(f"\n🔍 LỊCH SỬ PHÁT HIỆN CHO {args.mac}")
        print("="*60)
        
        for detection in detections[:args.limit] if args.limit else detections:
            time_str = datetime.fromisoformat(detection['detection_time']).strftime("%Y-%m-%d %H:%M:%S")
            print(f"⏰ {time_str} - Lần quét #{detection['scan_number']}")
        
        print("="*60)
        print(f"Tổng cộng: {len(detections)} lần phát hiện")
        
        if args.export_json:
            extractor.export_to_json(detections, args.export_json)

if __name__ == "__main__":
    main()