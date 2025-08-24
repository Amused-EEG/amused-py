"""
Muse S Exact Protocol Replication Client
This client exactly replicates the connection sequence from the pcap file
to ensure the sensor turns on correctly.

Based on pcap analysis showing the exact sequence of operations.
"""

import asyncio
import struct
from bleak import BleakClient, BleakScanner
import time
from typing import Optional
import sys

# Service UUID from pcap
MUSE_SERVICE_UUID = "0000fe8d-0000-1000-8000-00805f9b34fb"

# Characteristic UUIDs (from research files)
CONTROL_CHAR_UUID = "273e0001-4c4d-454d-96be-f03bac821358"
# We'll use a combined EEG characteristic for sensor data
SENSOR_CHAR_UUID = "273e0013-4c4d-454d-96be-f03bac821358"  # Combined EEG
# Alternative sensor characteristic if above doesn't work
ALT_SENSOR_CHAR_UUID = "273e0003-4c4d-454d-96be-f03bac821358"  # EEG TP9

# For direct handle access (we'll discover these)
HANDLES = {
    'control': None,
    'control_cccd': None,
    'sensor_data': None,
    'sensor1_cccd': None,
    'sensor2_cccd': None,
}

# Exact command sequence from pcap (including length prefix)
COMMANDS = {
    'v6': bytes.fromhex('0376360a'),      # Version info
    's': bytes.fromhex('02730a'),         # Status
    'h': bytes.fromhex('02680a'),         # Halt/stop
    'p21': bytes.fromhex('047032310a'),   # Preset 21 (from old capture)
    'dc001': bytes.fromhex('0664633030310a'), # Start streaming
    'L0': bytes.fromhex('034c300a'),      # L0 command (new capture)
    'L1': bytes.fromhex('034c310a'),      # L1 command
    'p1034': bytes.fromhex('0670313033340a'), # Preset 1034
    'p1035': bytes.fromhex('0670313033350a'), # Preset 1035 (new capture)
}

class MuseExactClient:
    """Client that exactly replicates the pcap connection sequence"""
    
    def __init__(self, verbose=True):
        self.client: Optional[BleakClient] = None
        self.verbose = verbose
        self.notifications_received = {
            'control': 0,
            'sensor': 0
        }
        self.is_streaming = False
        
    def log(self, message: str, level: str = "INFO"):
        """Log with timestamp"""
        if self.verbose:
            import datetime
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            symbols = {
                "INFO": "ℹ️",
                "SUCCESS": "✅",
                "ERROR": "❌",
                "SEND": "📤",
                "RECV": "📥",
                "WAIT": "⏱️"
            }
            symbol = symbols.get(level, "•")
            print(f"[{timestamp}] {symbol} {message}")
    
    def handle_control_notification(self, sender: int, data: bytearray):
        """Handle control characteristic notifications (0x0012)"""
        self.notifications_received['control'] += 1
        
        # Try to decode as text/JSON
        try:
            # Remove padding
            clean_data = data.rstrip(b'\x00')
            if clean_data and clean_data[0] > 127:  # Length byte
                clean_data = clean_data[1:]
            
            if b'{' in clean_data:
                # JSON response
                text = clean_data.decode('utf-8', errors='ignore')
                self.log(f"JSON Response: {text[:100]}...", "RECV")
            else:
                self.log(f"Control Response: {data.hex()}", "RECV")
        except:
            self.log(f"Control Data (hex): {data.hex()}", "RECV")
    
    def handle_sensor_notification(self, sender: int, data: bytearray):
        """Handle sensor data notifications (0x0018)"""
        self.notifications_received['sensor'] += 1
        
        if not self.is_streaming:
            self.is_streaming = True
            self.log("🎉 SENSOR STREAMING STARTED! 🎉", "SUCCESS")
        
        # Log first few packets to confirm
        if self.notifications_received['sensor'] <= 3:
            self.log(f"Sensor packet #{self.notifications_received['sensor']}: {len(data)} bytes, first bytes: {data[:8].hex()}", "RECV")
    
    async def find_device(self):
        """Scan for Muse device"""
        self.log("Scanning for Muse S device...", "INFO")
        
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: MUSE_SERVICE_UUID.lower() in ad.service_uuids,
            timeout=10
        )
        
        if device:
            self.log(f"Found: {device.name} ({device.address})", "SUCCESS")
        else:
            self.log("No Muse device found", "ERROR")
        
        return device
    
    async def discover_handles(self):
        """Discover and map handles to UUIDs"""
        self.log("Discovering services and characteristics...", "INFO")
        
        # Get all services
        services = self.client.services
        
        # Find our characteristics
        for service in services:
            if MUSE_SERVICE_UUID.lower() in service.uuid.lower():
                self.log(f"Found Muse service: {service.uuid}", "SUCCESS")
                
                for char in service.characteristics:
                    # Log all characteristics for debugging
                    self.log(f"  Char: {char.uuid}, Handle: {char.handle}, Properties: {char.properties}", "INFO")
                    
                    if CONTROL_CHAR_UUID.lower() in char.uuid.lower():
                        HANDLES['control'] = char.handle
                        self.log(f"  -> Control characteristic at handle {char.handle}", "SUCCESS")
                        
                        # Find CCCD for control
                        for descriptor in char.descriptors:
                            if "2902" in descriptor.uuid.lower():  # CCCD UUID
                                HANDLES['control_cccd'] = descriptor.handle
                                self.log(f"  -> Control CCCD at handle {descriptor.handle}", "SUCCESS")
        
        return HANDLES['control'] is not None
    
    async def replicate_exact_sequence(self):
        """
        Replicate the exact sequence from pcap:
        1. Enable control notifications
        2. Send v6 command
        3. Send s command  
        4. Send h command
        5. Send p21 command
        6. Send s command again
        7. Enable sensor notifications
        8. Send dc001 command (start streaming)
        9. Send L1 command
        """
        
        self.log("Starting exact pcap sequence replication", "INFO")
        
        try:
            # First discover handles
            if not await self.discover_handles():
                self.log("Failed to discover required characteristics", "ERROR")
                return False
            
            # Step 1: Enable control notifications using UUID
            self.log("Step 1: Enable control notifications", "SEND")
            await self.client.start_notify(CONTROL_CHAR_UUID, self.handle_control_notification)
            await asyncio.sleep(0.05)
            
            # Step 2: Send v6 command (frame 1106)
            self.log("Step 2: Send version command (v6)", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['v6'], response=False)
            await asyncio.sleep(0.1)  # Wait for response
            
            # Step 3: Send s command (frame 1122)
            self.log("Step 3: Send status command (s)", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['s'], response=False)
            await asyncio.sleep(0.05)
            
            # Step 4: Send h command (frame 1133)
            self.log("Step 4: Send halt command (h)", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['h'], response=False)
            await asyncio.sleep(0.05)
            
            # Step 5: Send p21 command (frame 1136)
            self.log("Step 5: Send preset command (p21)", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['p21'], response=False)
            await asyncio.sleep(0.05)
            
            # Step 6: Send s command again (frame 1139)
            self.log("Step 6: Send status command again (s)", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['s'], response=False)
            await asyncio.sleep(0.05)
            
            # Step 7: Try to enable sensor notifications
            # First try the combined characteristic
            try:
                self.log("Step 7: Trying to enable sensor notifications (0x0013)", "SEND")
                await self.client.start_notify(SENSOR_CHAR_UUID, self.handle_sensor_notification)
            except:
                # If that doesn't work, try the individual EEG characteristic
                self.log("Step 7: Trying alternative sensor characteristic (0x0003)", "SEND")
                try:
                    await self.client.start_notify(ALT_SENSOR_CHAR_UUID, self.handle_sensor_notification)
                except Exception as e:
                    self.log(f"Could not enable sensor notifications: {e}", "ERROR")
            
            await asyncio.sleep(0.05)
            
            # Step 9: Send dc001 command - START STREAMING! (frame 1160)
            self.log("Step 9: Send START STREAM command (dc001)", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'], response=False)
            await asyncio.sleep(0.025)  # Small delay for response
            
            # Step 10: Send L1 command (frame 1163)
            self.log("Step 10: Send L1 command", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['L1'], response=False)
            await asyncio.sleep(0.025)
            
            # Step 11: Send h command (frame 1165)
            self.log("Step 11: Send halt command", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['h'], response=False)
            await asyncio.sleep(0.025)
            
            # Step 12: Send p1034 command (frame 1168)
            self.log("Step 12: Send p1034 command", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['p1034'], response=False)
            await asyncio.sleep(0.025)
            
            # Step 13: Send s command (frame 1171)
            self.log("Step 13: Send status command", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['s'], response=False)
            await asyncio.sleep(0.25)  # Wait for status response
            
            # Step 14: Send dc001 AGAIN - this actually starts streaming! (frame 1190)
            self.log("Step 14: Send START STREAM command AGAIN (dc001)", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'], response=False)
            await asyncio.sleep(0.025)
            
            # Step 15: Send L1 command again (frame 1196)
            self.log("Step 15: Send L1 command again", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['L1'], response=False)
            
            # Wait to see if streaming starts (data starts at frame 1202)
            self.log("Waiting for sensor data to start...", "WAIT")
            await asyncio.sleep(1)
            
            if self.is_streaming:
                self.log(f"SUCCESS! Received {self.notifications_received['sensor']} sensor packets", "SUCCESS")
                return True
            else:
                self.log("No sensor data received - trying alternate sequence", "ERROR")
                
                # Try alternate commands from pcap
                self.log("Trying h command", "SEND")
                await self.client.write_gatt_char(HANDLES['control'], COMMANDS['h'], response=False)
                await asyncio.sleep(0.1)
                
                self.log("Trying p1034 command", "SEND")
                await self.client.write_gatt_char(HANDLES['control'], COMMANDS['p1034'], response=False)
                await asyncio.sleep(0.1)
                
                self.log("Trying dc001 again", "SEND")
                await self.client.write_gatt_char(HANDLES['control'], COMMANDS['dc001'], response=False)
                await asyncio.sleep(2)
                
                return self.is_streaming
                
        except Exception as e:
            self.log(f"Error in sequence: {e}", "ERROR")
            return False
    
    async def connect_and_start(self, address: str):
        """Connect to device and start streaming"""
        self.log(f"Connecting to {address}...", "INFO")
        
        self.client = BleakClient(address)
        
        try:
            await self.client.connect()
            
            if not self.client.is_connected:
                self.log("Failed to connect", "ERROR")
                return False
            
            self.log("Connected successfully", "SUCCESS")
            
            # Execute the exact sequence
            success = await self.replicate_exact_sequence()
            
            if success:
                self.log("✨ Sensor is streaming! ✨", "SUCCESS")
                
                # Keep streaming for a while
                self.log("Streaming for 10 seconds...", "INFO")
                await asyncio.sleep(10)
                
                # Stop streaming
                self.log("Sending stop command", "SEND")
                await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['h'], response=False)
                await asyncio.sleep(0.5)
            
            return success
            
        except Exception as e:
            self.log(f"Connection error: {e}", "ERROR")
            return False
        finally:
            if self.client and self.client.is_connected:
                await self.client.disconnect()
                self.log("Disconnected", "INFO")

async def main():
    """Main function"""
    print("=" * 60)
    print("Muse S Exact Protocol Replication Client")
    print("This will replicate the exact sequence from the pcap file")
    print("=" * 60)
    
    client = MuseExactClient(verbose=True)
    
    # Find device
    device = await client.find_device()
    if not device:
        print("\n❌ Please ensure your Muse S is on and in pairing mode")
        return
    
    # Connect and start
    success = await client.connect_and_start(device.address)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print(f"  Control notifications received: {client.notifications_received['control']}")
    print(f"  Sensor packets received: {client.notifications_received['sensor']}")
    print(f"  Streaming successful: {'YES ✅' if success else 'NO ❌'}")
    print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)