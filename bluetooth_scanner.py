#!/usr/bin/env python3
"""
Bluetooth Scanner với tính năng ước tính khoảng cách
Yêu cầu: pip install bleak asyncio
"""

import asyncio
import math
from datetime import datetime
from typing import Dict, List
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

class BluetoothScanner:
    def __init__(self):
        # Hằng số để tính khoảng cách
        self.MEASURED_POWER = -59  # RSSI tại 1 mét (có thể điều chỉnh theo thiết bị)
        self.PATH_LOSS_EXPONENT = 2.0  # Hệ số suy hao (2-4 tùy môi trường)
        self.discovered_devices: Dict[str, Dict] = {}
        self.scanner = None
        
    def calculate_distance(self, rssi: int, measured_power: int = None) -> float:
        """
        Tính khoảng cách dựa trên RSSI
        Công thức: Distance = 10^((Measured Power - RSSI) / (10 * n))
        """
        if measured_power is None:
            measured_power = self.MEASURED_POWER
            
        if rssi == 0:
            return -1.0  # Cannot determine distance
            
        distance = math.pow(10, (measured_power - rssi) / (10 * self.PATH_LOSS_EXPONENT))
        return round(distance, 2)
    
    def get_distance_accuracy(self, distance: float) -> str:
        """Đánh giá độ chính xác của khoảng cách"""
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
    
    def format_device_info(self, device: BLEDevice, advertisement_data: AdvertisementData) -> Dict:
        """Format thông tin thiết bị"""
        rssi = advertisement_data.rssi if advertisement_data else -100
        distance = self.calculate_distance(rssi)
        
        return {
            'address': device.address,
            'name': device.name or 'Unknown Device',
            'rssi': rssi,
            'distance_meters': distance,
            'distance_accuracy': self.get_distance_accuracy(distance),
            'tx_power': advertisement_data.tx_power if advertisement_data else None,
            'manufacturer_data': self._format_manufacturer_data(advertisement_data),
            'service_uuids': list(advertisement_data.service_uuids) if advertisement_data else [],
            'service_data': self._format_service_data(advertisement_data),
            'last_seen': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def _format_manufacturer_data(self, advertisement_data: AdvertisementData) -> Dict:
        """Format manufacturer data"""
        if not advertisement_data or not advertisement_data.manufacturer_data:
            return {}
            
        formatted = {}
        for company_id, data in advertisement_data.manufacturer_data.items():
            company_name = self._get_company_name(company_id)
            formatted[f"{company_name} ({hex(company_id)})"] = data.hex()
        return formatted
    
    def _format_service_data(self, advertisement_data: AdvertisementData) -> Dict:
        """Format service data"""
        if not advertisement_data or not advertisement_data.service_data:
            return {}
            
        formatted = {}
        for uuid, data in advertisement_data.service_data.items():
            formatted[uuid] = data.hex()
        return formatted
    
    def _get_company_name(self, company_id: int) -> str:
        """Lấy tên công ty từ ID (một số ID phổ biến)"""
        companies = {
            0x004C: "Apple",
            0x0006: "Microsoft",
            0x00E0: "Google",
            0x0075: "Samsung",
            0x001D: "Qualcomm",
            0x0157: "Xiaomi",
            0x02D0: "Huawei",
        }
        return companies.get(company_id, "Unknown")
    
    def display_devices(self):
        """Hiển thị danh sách thiết bị"""
        print("\033[2J\033[H")  # Clear screen
        print("=" * 80)
        print("BLUETOOTH SCANNER - PYTHON")
        print(f"Đã phát hiện: {len(self.discovered_devices)} thiết bị")
        print("=" * 80)
        
        # Sắp xếp theo khoảng cách
        sorted_devices = sorted(
            self.discovered_devices.values(),
            key=lambda x: x['distance_meters'] if x['distance_meters'] > 0 else float('inf')
        )
        
        for idx, device in enumerate(sorted_devices, 1):
            print(f"\n[{idx}] {device['name']}")
            print(f"    Địa chỉ: {device['address']}")
            print(f"    RSSI: {device['rssi']} dBm")
            print(f"    Khoảng cách: ~{device['distance_meters']} mét ({device['distance_accuracy']})")
            
            if device['tx_power']:
                print(f"    TX Power: {device['tx_power']} dBm")
                
            if device['service_uuids']:
                print(f"    Services: {', '.join(device['service_uuids'][:3])}")
                
            if device['manufacturer_data']:
                for company, data in device['manufacturer_data'].items():
                    print(f"    Manufacturer: {company}")
                    if len(data) <= 20:
                        print(f"    Data: {data}")
            
            print(f"    Lần cuối thấy: {device['last_seen']}")
    
    async def detection_callback(self, device: BLEDevice, advertisement_data: AdvertisementData):
        """Callback khi phát hiện thiết bị"""
        device_info = self.format_device_info(device, advertisement_data)
        self.discovered_devices[device.address] = device_info
        self.display_devices()
    
    async def run_scanner(self, duration: int = 0):
        """
        Chạy scanner
        duration: thời gian scan (0 = vô hạn)
        """
        print("Đang khởi động Bluetooth scanner...")
        print("Nhấn Ctrl+C để dừng\n")
        
        try:
            scanner = BleakScanner(self.detection_callback)
            await scanner.start()
            
            if duration > 0:
                await asyncio.sleep(duration)
            else:
                # Scan vô hạn
                while True:
                    await asyncio.sleep(1)
                    
        except KeyboardInterrupt:
            print("\n\nĐang dừng scanner...")
        finally:
            await scanner.stop()
            self.export_results()
    
    def export_results(self):
        """Xuất kết quả"""
        print("\n" + "=" * 80)
        print("KẾT QUẢ SCAN CUỐI CÙNG")
        print("=" * 80)
        
        if not self.discovered_devices:
            print("Không tìm thấy thiết bị nào.")
            return
        
        # Thống kê
        print(f"\nTổng số thiết bị: {len(self.discovered_devices)}")
        
        # Phân loại theo khoảng cách
        very_close = sum(1 for d in self.discovered_devices.values() if d['distance_meters'] <= 1)
        close = sum(1 for d in self.discovered_devices.values() if 1 < d['distance_meters'] <= 3)
        medium = sum(1 for d in self.discovered_devices.values() if 3 < d['distance_meters'] <= 10)
        far = sum(1 for d in self.discovered_devices.values() if d['distance_meters'] > 10)
        
        print(f"  - Rất gần (≤1m): {very_close}")
        print(f"  - Gần (1-3m): {close}")
        print(f"  - Trung bình (3-10m): {medium}")
        print(f"  - Xa (>10m): {far}")
        
        # Lưu kết quả vào file
        import json
        filename = f"bluetooth_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(list(self.discovered_devices.values()), f, indent=2, ensure_ascii=False)
        
        print(f"\nKết quả đã được lưu vào: {filename}")

async def main():
    """Hàm chính"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Bluetooth Scanner với tính khoảng cách')
    parser.add_argument('-t', '--time', type=int, default=0,
                       help='Thời gian scan (giây). 0 = vô hạn')
    parser.add_argument('-p', '--power', type=int, default=-59,
                       help='Measured power (RSSI tại 1m)')
    parser.add_argument('-n', '--path-loss', type=float, default=2.0,
                       help='Path loss exponent (2.0-4.0)')
    
    args = parser.parse_args()
    
    scanner = BluetoothScanner()
    scanner.MEASURED_POWER = args.power
    scanner.PATH_LOSS_EXPONENT = args.path_loss
    
    await scanner.run_scanner(args.time)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScanner đã dừng.")
    except Exception as e:
        print(f"Lỗi: {e}")
        print("\nĐảm bảo đã cài đặt thư viện: pip install bleak")