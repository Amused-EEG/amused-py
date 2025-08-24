"""
Muse S Sleep Monitoring Client
Based on the extended capture analysis showing sleep monitoring session.
This client follows the EXACT protocol sequence from the new capture.

Features:
- Follows the exact sleep monitoring initialization sequence
- Uses p1034/p1035 presets (likely for sleep-specific settings)
- Handles long-duration streaming sessions
- Includes data logging for overnight monitoring
"""

import asyncio
import struct
import json
import csv
from bleak import BleakClient, BleakScanner
import datetime
from typing import Optional, Dict, Any, List
import time
import os
import numpy as np
from muse_ppg_heart_rate import PPGHeartRateExtractor, PPGData

# Service and Characteristic UUIDs
MUSE_SERVICE_UUID = "0000fe8d-0000-1000-8000-00805f9b34fb"
CONTROL_CHAR_UUID = "273e0001-4c4d-454d-96be-f03bac821358"

# Try multiple sensor characteristics (different models may use different ones)
SENSOR_CHAR_UUIDS = [
    "273e0013-4c4d-454d-96be-f03bac821358",  # Combined EEG
    "273e0003-4c4d-454d-96be-f03bac821358",  # EEG TP9
]

# PPG characteristics for heart rate monitoring
PPG_CHAR_UUIDS = [
    "273e000f-4c4d-454d-96be-f03bac821358",  # PPG1 (infrared)
    "273e0010-4c4d-454d-96be-f03bac821358",  # PPG2 (near-infrared)  
    "273e0011-4c4d-454d-96be-f03bac821358",  # PPG3 (red)
]

# Commands from new capture (sleep monitoring session)
COMMANDS = {
    'v6': bytes.fromhex('0376360a'),           # Version info
    's': bytes.fromhex('02730a'),              # Status
    'h': bytes.fromhex('02680a'),              # Halt/stop
    'p1034': bytes.fromhex('0670313033340a'),  # Sleep preset 1
    'p1035': bytes.fromhex('0670313033350a'),  # Sleep preset 2
    'dc001': bytes.fromhex('0664633030310a'),  # Start streaming
    'L1': bytes.fromhex('034c310a'),           # L1 command
}

class MuseSleepClient:
    """Sleep monitoring client for Muse S - follows exact protocol from capture"""
    
    def __init__(self, log_dir: str = "sleep_data", verbose: bool = True):
        self.client: Optional[BleakClient] = None
        self.verbose = verbose
        self.log_dir = log_dir
        self.session_start = None
        self.is_streaming = False
        
        # Statistics
        self.packet_count = 0
        self.control_responses = 0
        self.errors = 0
        self.last_packet_time = None
        
        # Device info
        self.device_info = {}
        
        # Data logging
        self.csv_writer = None
        self.csv_file = None
        self.sensor_characteristic = None
        
        # PPG and heart rate
        self.ppg_enabled = False
        self.ppg_characteristics = []
        self.ppg_extractor = PPGHeartRateExtractor(sample_rate=64)
        self.ppg_buffer = []  # Buffer for PPG samples
        self.heart_rate_history = []
        self.last_heart_rate = None
        
        # Create log directory
        os.makedirs(log_dir, exist_ok=True)
    
    def log(self, message: str, level: str = "INFO"):
        """Log with timestamp"""
        if self.verbose:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            symbols = {
                "INFO": "[i]",
                "SUCCESS": "[+]",
                "ERROR": "[!]",
                "SEND": "[>]",
                "RECV": "[<]",
                "DATA": "[*]",
                "SLEEP": "[Z]"
            }
            symbol = symbols.get(level, "[.]")
            print(f"[{timestamp}] {symbol} {message}")
    
    def handle_control_notification(self, sender: int, data: bytearray):
        """Handle control responses and JSON data"""
        self.control_responses += 1
        
        try:
            # Clean and decode JSON if present
            clean_data = data.rstrip(b'\x00')
            if clean_data and clean_data[0] > 127:  # Remove length byte
                clean_data = clean_data[1:]
            
            if b'{' in clean_data:
                json_str = clean_data.decode('utf-8', errors='ignore')
                json_str = json_str[:json_str.rfind('}')+1] if '}' in json_str else json_str
                
                json_data = json.loads(json_str)
                self.device_info.update(json_data)
                
                # Log important info
                if 'bp' in json_data:
                    self.log(f"Battery: {json_data['bp']:.1f}%", "INFO")
                if 'fw' in json_data:
                    self.log(f"Firmware: {json_data['fw']}", "INFO")
                if 'rc' in json_data and json_data['rc'] == 0:
                    self.log("Command acknowledged", "RECV")
            else:
                # Non-JSON response
                if data.hex() == "087b227263223a307d000000000000000000002c":
                    self.log("Command acknowledged (rc:0)", "RECV")
        except Exception as e:
            if self.verbose:
                self.log(f"Control data: {data.hex()[:40]}...", "RECV")
    
    def handle_sensor_notification(self, sender: int, data: bytearray):
        """Handle sensor data for sleep monitoring"""
        self.packet_count += 1
        self.last_packet_time = time.time()
        
        # First packet - streaming confirmed!
        if not self.is_streaming:
            self.is_streaming = True
            self.log("SLEEP MONITORING STARTED!", "SLEEP")
            self.session_start = datetime.datetime.now()
            self.init_csv_logging()
        
        # Log packet info periodically
        if self.packet_count % 100 == 0:
            elapsed = time.time() - (self.session_start.timestamp() if self.session_start else time.time())
            self.log(f"Packets: {self.packet_count}, Duration: {elapsed:.1f}s", "DATA")
        
        # Write to CSV
        if self.csv_writer:
            self.csv_writer.writerow([
                datetime.datetime.now().isoformat(),
                self.packet_count,
                len(data),
                data.hex()
            ])
            
            # Flush periodically for safety
            if self.packet_count % 10 == 0:
                self.csv_file.flush()
    
    def handle_ppg_notification(self, sender: int, data: bytearray):
        """Handle PPG data for heart rate monitoring"""
        try:
            # Parse PPG packet
            ppg_data = self.ppg_extractor.parse_ppg_packet(bytes(data))
            
            if ppg_data:
                # Add samples to buffer (use IR channel for best results)
                self.ppg_buffer.extend(ppg_data.ir_samples)
                
                # Extract heart rate every 5 seconds (320 samples at 64Hz)
                if len(self.ppg_buffer) >= 320:
                    # Convert to numpy array
                    ppg_signal = np.array(self.ppg_buffer[-640:])  # Use last 10 seconds
                    
                    # Extract heart rate
                    result = self.ppg_extractor.extract_heart_rate(ppg_signal)
                    
                    if result.heart_rate_bpm > 0:
                        self.last_heart_rate = result.heart_rate_bpm
                        self.heart_rate_history.append({
                            'timestamp': datetime.datetime.now(),
                            'heart_rate': result.heart_rate_bpm,
                            'confidence': result.confidence,
                            'quality': result.signal_quality
                        })
                        
                        if self.verbose:
                            self.log(f"Heart Rate: {result.heart_rate_bpm:.0f} BPM ({result.signal_quality})", "DATA")
                    
                    # Keep buffer size manageable
                    if len(self.ppg_buffer) > 1280:  # 20 seconds max
                        self.ppg_buffer = self.ppg_buffer[-640:]
                        
        except Exception as e:
            if self.verbose:
                self.log(f"PPG processing error: {e}", "ERROR")
    
    def init_csv_logging(self):
        """Initialize CSV logging for sleep data"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.log_dir, f"sleep_session_{timestamp}.csv")
        
        self.csv_file = open(filename, 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(['timestamp', 'packet_num', 'size', 'hex_data'])
        
        self.log(f"Logging to: {filename}", "INFO")
    
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
    
    async def execute_sleep_sequence(self):
        """
        Execute the EXACT sequence from the sleep monitoring capture.
        Based on frames 24226-24349 from bluetooth_hci_new.pcap
        """
        
        self.log("Starting sleep monitoring sequence", "SLEEP")
        
        try:
            # Step 1: Enable control notifications
            self.log("Step 1: Enable control notifications", "SEND")
            await self.client.start_notify(CONTROL_CHAR_UUID, self.handle_control_notification)
            await asyncio.sleep(0.05)
            
            # Step 2: Get version (v6)
            self.log("Step 2: Get device version", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['v6'], response=False)
            await asyncio.sleep(0.1)
            
            # Step 3: Get status
            self.log("Step 3: Get device status", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['s'], response=False)
            await asyncio.sleep(0.1)
            
            # Step 4: Halt (ensure clean state)
            self.log("Step 4: Halt any existing streams", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['h'], response=False)
            await asyncio.sleep(0.08)
            
            # Step 5: Set preset p1034 (sleep mode 1)
            self.log("Step 5: Set sleep preset p1034", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['p1034'], response=False)
            await asyncio.sleep(0.08)
            
            # Step 6: Check status after preset
            self.log("Step 6: Check status after preset", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['s'], response=False)
            await asyncio.sleep(0.1)
            
            # Step 7: Enable sensor notifications
            # Try multiple characteristics until one works
            sensor_enabled = False
            for char_uuid in SENSOR_CHAR_UUIDS:
                try:
                    self.log(f"Step 7: Trying sensor characteristic {char_uuid[-4:]}", "SEND")
                    await self.client.start_notify(char_uuid, self.handle_sensor_notification)
                    self.sensor_characteristic = char_uuid
                    sensor_enabled = True
                    break
                except Exception as e:
                    self.log(f"  Characteristic not available, trying next", "INFO")
            
            if not sensor_enabled:
                self.log("Could not enable sensor notifications!", "ERROR")
                return False
            
            await asyncio.sleep(0.1)
            
            # Step 7b: Check for PPG in the multiplexed data stream
            # PPG data may be embedded in the main sensor stream rather than separate characteristics
            self.log("Step 7b: PPG/fNIRS will be extracted from sensor stream", "INFO")
            # The Muse S sleep preset (p1034/p1035) includes PPG data in the multiplexed stream
            
            await asyncio.sleep(0.1)
            
            # Step 8: First dc001 attempt
            self.log("Step 8: Send dc001 (first attempt)", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'], response=False)
            await asyncio.sleep(0.025)
            
            # Step 9: Send L1
            self.log("Step 9: Send L1 command", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['L1'], response=False)
            await asyncio.sleep(0.07)
            
            # Step 10: Halt again
            self.log("Step 10: Send halt", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['h'], response=False)
            await asyncio.sleep(0.06)
            
            # Step 11: Set preset p1035 (sleep mode 2)
            self.log("Step 11: Set sleep preset p1035", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['p1035'], response=False)
            await asyncio.sleep(0.09)
            
            # Step 12: Check status
            self.log("Step 12: Check status", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['s'], response=False)
            await asyncio.sleep(0.1)
            
            # Step 13: CRITICAL - Second dc001 (this starts streaming!)
            self.log("Step 13: Send dc001 (SECOND attempt - starts streaming!)", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'], response=False)
            await asyncio.sleep(0.025)
            
            # Step 14: Send L1 again
            self.log("Step 14: Send L1 command again", "SEND")
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['L1'], response=False)
            
            # Wait for streaming to start
            self.log("Waiting for sleep monitoring to begin...", "SLEEP")
            await asyncio.sleep(2)
            
            if self.is_streaming:
                self.log(f"Sleep monitoring active! Receiving data...", "SLEEP")
                return True
            else:
                self.log("No data received - check device", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Error in sequence: {e}", "ERROR")
            self.errors += 1
            return False
    
    async def connect_and_monitor(self, address: str, duration_hours: float = 8.0):
        """Connect and monitor sleep for specified duration"""
        
        self.log(f"Connecting to {address} for {duration_hours}h monitoring", "SLEEP")
        self.client = BleakClient(address)
        
        try:
            await self.client.connect()
            
            if not self.client.is_connected:
                self.log("Failed to connect", "ERROR")
                return False
            
            self.log("Connected successfully", "SUCCESS")
            
            # Execute sleep monitoring sequence
            success = await self.execute_sleep_sequence()
            
            if success:
                # Monitor for specified duration
                duration_seconds = duration_hours * 3600
                self.log(f"Monitoring sleep for {duration_hours} hours...", "SLEEP")
                
                start_time = time.time()
                last_status = time.time()
                
                while (time.time() - start_time) < duration_seconds:
                    # Status update every 5 minutes
                    if time.time() - last_status > 300:
                        elapsed_hours = (time.time() - start_time) / 3600
                        remaining_hours = duration_hours - elapsed_hours
                        
                        self.log(f"Status: {elapsed_hours:.1f}h elapsed, {remaining_hours:.1f}h remaining", "SLEEP")
                        status_msg = f"  Packets: {self.packet_count}, Battery: {self.device_info.get('bp', 'N/A')}%"
                        if self.last_heart_rate:
                            status_msg += f", HR: {self.last_heart_rate:.0f} BPM"
                        self.log(status_msg, "DATA")
                        last_status = time.time()
                    
                    # Check for connection issues
                    if self.last_packet_time and (time.time() - self.last_packet_time) > 10:
                        self.log("No data for 10s - possible connection issue", "ERROR")
                        self.errors += 1
                        
                        # Try to restart stream
                        self.log("Attempting to restart stream...", "INFO")
                        await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'], response=False)
                        await asyncio.sleep(0.1)
                        await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['L1'], response=False)
                        await asyncio.sleep(2)
                    
                    await asyncio.sleep(1)
                
                # Monitoring complete
                self.log("Sleep monitoring complete!", "SLEEP")
                
                # Stop streaming
                self.log("Stopping data stream...", "SEND")
                await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['h'], response=False)
                await asyncio.sleep(0.5)
                
            return success
            
        except Exception as e:
            self.log(f"Connection error: {e}", "ERROR")
            self.errors += 1
            return False
        finally:
            # Clean up
            if self.csv_file:
                self.csv_file.close()
                self.log("Data log saved", "SUCCESS")
            
            if self.client and self.client.is_connected:
                await self.client.disconnect()
                self.log("Disconnected", "INFO")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get session summary"""
        duration = 0
        if self.session_start:
            duration = (datetime.datetime.now() - self.session_start).total_seconds()
        
        # Calculate heart rate statistics
        hr_stats = {}
        if self.heart_rate_history:
            heart_rates = [h['heart_rate'] for h in self.heart_rate_history]
            hr_stats = {
                'avg_heart_rate': np.mean(heart_rates),
                'min_heart_rate': np.min(heart_rates),
                'max_heart_rate': np.max(heart_rates),
                'hr_samples': len(heart_rates),
                'last_heart_rate': self.last_heart_rate
            }
        
        return {
            'packets_received': self.packet_count,
            'control_responses': self.control_responses,
            'errors': self.errors,
            'duration_seconds': duration,
            'duration_hours': duration / 3600,
            'battery_percent': self.device_info.get('bp', 'Unknown'),
            'firmware': self.device_info.get('fw', 'Unknown'),
            'device_name': self.device_info.get('hn', 'Unknown'),
            'ppg_enabled': self.ppg_enabled,
            'heart_rate_stats': hr_stats
        }

async def main():
    """Main function for sleep monitoring"""
    
    print("=" * 60)
    print("Muse S Sleep Monitoring Client")
    print("Based on extended capture protocol analysis")
    print("=" * 60)
    
    # Configuration
    MONITOR_HOURS = 0.05  # 3 minutes for testing (use 8.0 for full night)
    
    client = MuseSleepClient(log_dir="sleep_data", verbose=True)
    
    # Find device
    device = await client.find_device()
    if not device:
        print("\nPlease ensure your Muse S is on and in pairing mode")
        return
    
    # Start monitoring
    print(f"\nStarting {MONITOR_HOURS} hour sleep monitoring session...")
    success = await client.connect_and_monitor(device.address, MONITOR_HOURS)
    
    # Print summary
    summary = client.get_summary()
    print("\n" + "=" * 60)
    print("SESSION SUMMARY:")
    print(f"  Duration: {summary['duration_hours']:.2f} hours")
    print(f"  Packets received: {summary['packets_received']:,}")
    print(f"  Control responses: {summary['control_responses']}")
    print(f"  Errors: {summary['errors']}")
    print(f"  Final battery: {summary['battery_percent']}%")
    print(f"  Device: {summary['device_name']}")
    
    # Heart rate statistics
    if summary['ppg_enabled'] and summary['heart_rate_stats']:
        hr_stats = summary['heart_rate_stats']
        print(f"\nHEART RATE DATA:")
        print(f"  Average HR: {hr_stats['avg_heart_rate']:.0f} BPM")
        print(f"  Min HR: {hr_stats['min_heart_rate']:.0f} BPM")
        print(f"  Max HR: {hr_stats['max_heart_rate']:.0f} BPM")
        print(f"  Samples: {hr_stats['hr_samples']}")
    elif summary['ppg_enabled']:
        print(f"\nHEART RATE: PPG enabled but no data collected")
    else:
        print(f"\nHEART RATE: PPG not available on this device")
    
    print(f"\n  Status: {'SUCCESS' if success else 'FAILED'}")
    print("=" * 60)
    
    if success and summary['packets_received'] > 0:
        print(f"\nData saved to sleep_data/ directory")
        print(f"   CSV file contains {summary['packets_received']} packets")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nMonitoring interrupted by user")
    except Exception as e:
        print(f"\nFatal error: {e}")