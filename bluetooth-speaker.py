#!/usr/bin/env python3
"""
Bluetooth Speaker Service for OrangePi Zero3
Nhận lệnh từ Flutter app để kết nối/disconnect loa Bluetooth
"""

import asyncio
import json
import subprocess
import time
from bleak import BleakServer, BleakCharacteristic
from bleak.uuids import uuid16_dict
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Service và Characteristic UUIDs
SPEAKER_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef3"
SPEAKER_COMMAND_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef4"
SPEAKER_STATUS_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef5"

class BluetoothSpeakerService:
    def __init__(self):
        self.server = None
        self.status_char = None
        self.connected_speakers = []

    async def setup_server(self):
        """Setup BLE server"""

        async def command_handler(characteristic, data):
            """Xử lý lệnh từ Flutter app"""
            try:
                command = json.loads(data.decode())
                logger.info(f"Received command: {command}")

                if command.get('action') == 'scan_speakers':
                    await self.scan_bluetooth_speakers()
                elif command.get('action') == 'connect_speaker':
                    mac_address = command.get('mac_address')
                    await self.connect_speaker(mac_address)
                elif command.get('action') == 'disconnect_speaker':
                    mac_address = command.get('mac_address')
                    await self.disconnect_speaker(mac_address)
                elif command.get('action') == 'list_speakers':
                    await self.list_connected_speakers()

            except Exception as e:
                logger.error(f"Error handling command: {e}")
                await self.send_status(f"error: {str(e)}")

        # Tạo service
        service = BleakServer()

        # Command characteristic (nhận lệnh từ app)
        command_char = BleakCharacteristic(
            SPEAKER_COMMAND_CHAR_UUID,
            properties=["write"],
            value=None,
            descriptors=None
        )
        command_char.add_write_handler(command_handler)

        # Status characteristic (gửi status về app)
        self.status_char = BleakCharacteristic(
            SPEAKER_STATUS_CHAR_UUID,
            properties=["notify", "read"],
            value=b"ready",
            descriptors=None
        )

        # Thêm characteristics vào service
        service.add_service(SPEAKER_SERVICE_UUID)
        service.add_characteristic(command_char)
        service.add_characteristic(self.status_char)

        self.server = service

    async def scan_bluetooth_speakers(self):
        """Scan và tìm loa Bluetooth"""
        try:
            logger.info("Scanning for Bluetooth speakers...")

            # Sử dụng bluetoothctl để scan
            result = subprocess.run([
                'bluetoothctl', '--timeout=10', 'scan', 'on'
            ], capture_output=True, text=True, timeout=15)

            # Đợi một chút để scan
            await asyncio.sleep(10)

            # Lấy danh sách devices
            result = subprocess.run([
                'bluetoothctl', 'devices'
            ], capture_output=True, text=True)

            devices = []
            for line in result.stdout.split('\n'):
                if line.strip() and 'Device' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = ' '.join(parts[2:])
                        devices.append({'mac': mac, 'name': name})

            response = {
                'action': 'scan_result',
                'devices': devices
            }

            await self.send_status(json.dumps(response))

        except Exception as e:
            logger.error(f"Error scanning speakers: {e}")
            await self.send_status(f"scan_error: {str(e)}")

    async def connect_speaker(self, mac_address):
        """Kết nối tới loa Bluetooth"""
        try:
            logger.info(f"Connecting to speaker: {mac_address}")

            # Trust device
            subprocess.run(['bluetoothctl', 'trust', mac_address])

            # Pair device
            pair_result = subprocess.run([
                'bluetoothctl', 'pair', mac_address
            ], capture_output=True, text=True, timeout=30)

            # Connect device
            connect_result = subprocess.run([
                'bluetoothctl', 'connect', mac_address
            ], capture_output=True, text=True, timeout=20)

            if connect_result.returncode == 0:
                # Set as default audio sink
                subprocess.run(['pactl', 'set-default-sink', f'bluez_sink.{mac_address.replace(":", "_")}.a2dp_sink'])

                self.connected_speakers.append(mac_address)
                await self.send_status(f"connected: {mac_address}")
                logger.info(f"Successfully connected to {mac_address}")
            else:
                await self.send_status(f"connect_failed: {mac_address}")
                logger.error(f"Failed to connect to {mac_address}")

        except Exception as e:
            logger.error(f"Error connecting speaker: {e}")
            await self.send_status(f"connect_error: {str(e)}")

    async def disconnect_speaker(self, mac_address):
        """Ngắt kết nối loa Bluetooth"""
        try:
            logger.info(f"Disconnecting speaker: {mac_address}")

            result = subprocess.run([
                'bluetoothctl', 'disconnect', mac_address
            ], capture_output=True, text=True)

            if result.returncode == 0:
                if mac_address in self.connected_speakers:
                    self.connected_speakers.remove(mac_address)
                await self.send_status(f"disconnected: {mac_address}")
            else:
                await self.send_status(f"disconnect_failed: {mac_address}")

        except Exception as e:
            logger.error(f"Error disconnecting speaker: {e}")
            await self.send_status(f"disconnect_error: {str(e)}")

    async def list_connected_speakers(self):
        """Liệt kê loa đã kết nối"""
        try:
            result = subprocess.run([
                'bluetoothctl', 'info'
            ], capture_output=True, text=True)

            response = {
                'action': 'connected_speakers',
                'speakers': self.connected_speakers
            }

            await self.send_status(json.dumps(response))

        except Exception as e:
            logger.error(f"Error listing speakers: {e}")
            await self.send_status(f"list_error: {str(e)}")

    async def send_status(self, message):
        """Gửi status về Flutter app"""
        if self.status_char:
            await self.status_char.notify(message.encode())

    async def start_server(self):
        """Start BLE server"""
        await self.setup_server()
        await self.server.start()
        logger.info("Bluetooth Speaker Service started")

        # Keep server running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            await self.server.stop()

async def main():
    service = BluetoothSpeakerService()
    await service.start_server()

if __name__ == "__main__":
    asyncio.run(main())
