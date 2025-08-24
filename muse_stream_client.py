"""
Muse Stream Client with Binary Storage
Efficient streaming with real-time processing and compact binary storage

This client combines the best of both worlds:
- Real-time data processing and callbacks
- Efficient binary storage (10x smaller than CSV)
- On-the-fly decoding when needed
"""

import asyncio
from bleak import BleakClient, BleakScanner
import datetime
from typing import Optional, Callable, Dict, Any
import os

from muse_raw_stream import MuseRawStream
from muse_realtime_decoder import MuseRealtimeDecoder, DecodedData

# BLE UUIDs
MUSE_SERVICE_UUID = "0000fe8d-0000-1000-8000-00805f9b34fb"
CONTROL_CHAR_UUID = "273e0001-4c4d-454d-96be-f03bac821358"
SENSOR_CHAR_UUIDS = [
    "273e0013-4c4d-454d-96be-f03bac821358",  # Combined sensors
    "273e0003-4c4d-454d-96be-f03bac821358",  # EEG TP9
]

# Commands
COMMANDS = {
    'v6': bytes.fromhex('0376360a'),           # Version
    's': bytes.fromhex('02730a'),              # Status
    'h': bytes.fromhex('02680a'),              # Halt
    'p21': bytes.fromhex('047032310a'),        # Basic preset
    'p1034': bytes.fromhex('0670313033340a'),  # Sleep preset
    'p1035': bytes.fromhex('0670313033350a'),  # Sleep preset 2
    'dc001': bytes.fromhex('0664633030310a'),  # Start streaming
    'L1': bytes.fromhex('034c310a'),           # L1 command
}

class MuseStreamClient:
    """
    Modern Muse S client with binary storage and real-time processing
    
    Features:
    - Saves raw data in compact binary format
    - Real-time decoding with callbacks
    - Simple API for researchers
    - Automatic file management
    """
    
    def __init__(self, 
                 save_raw: bool = False,  # Default to NOT saving
                 decode_realtime: bool = True,
                 data_dir: str = "muse_data",
                 verbose: bool = True):
        """
        Initialize streaming client
        
        Args:
            save_raw: Save raw binary data to file (default: False)
            decode_realtime: Decode packets in real-time (default: True)
            data_dir: Directory for data files (only created if save_raw=True)
            verbose: Print status messages
        """
        self.save_raw = save_raw
        self.decode_realtime = decode_realtime
        self.data_dir = data_dir
        self.verbose = verbose
        
        # Only create data directory if we're saving
        if save_raw:
            os.makedirs(data_dir, exist_ok=True)
        
        # BLE client
        self.client: Optional[BleakClient] = None
        
        # Raw stream handler
        self.raw_stream: Optional[MuseRawStream] = None
        
        # Real-time decoder
        self.decoder = MuseRealtimeDecoder() if decode_realtime else None
        
        # Session info
        self.session_start = None
        self.is_streaming = False
        self.packet_count = 0
        
        # Device info
        self.device_info = {}
        
        # User callbacks
        self.user_callbacks = {
            'eeg': None,
            'ppg': None,
            'imu': None,
            'heart_rate': None,
            'packet': None  # Called for every packet
        }
    
    def on_eeg(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback for EEG data"""
        self.user_callbacks['eeg'] = callback
        if self.decoder:
            self.decoder.register_callback('eeg', 
                lambda data: callback({'channels': data.eeg, 'timestamp': data.timestamp}))
    
    def on_ppg(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback for PPG data"""
        self.user_callbacks['ppg'] = callback
        if self.decoder:
            self.decoder.register_callback('ppg',
                lambda data: callback({'samples': data.ppg, 'timestamp': data.timestamp}))
    
    def on_heart_rate(self, callback: Callable[[float], None]):
        """Register callback for heart rate"""
        self.user_callbacks['heart_rate'] = callback
        if self.decoder:
            self.decoder.register_callback('heart_rate',
                lambda data: callback(data.heart_rate))
    
    def on_imu(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback for IMU data"""
        self.user_callbacks['imu'] = callback
        if self.decoder:
            self.decoder.register_callback('imu',
                lambda data: callback({'accel': data.imu.get('accel'), 'gyro': data.imu.get('gyro')}))
    
    def on_packet(self, callback: Callable[[bytes], None]):
        """Register callback for raw packets"""
        self.user_callbacks['packet'] = callback
    
    def log(self, message: str, level: str = "INFO"):
        """Log message with timestamp"""
        if self.verbose:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] {message}")
    
    async def find_device(self, name_filter: str = "Muse") -> Optional[Any]:
        """Find Muse device
        
        Args:
            name_filter: Name filter for device search
        
        Returns:
            Device object or None
        """
        self.log("Scanning for Muse devices...")
        devices = await BleakScanner.discover(timeout=5.0)
        
        for device in devices:
            if device.name and name_filter in device.name:
                self.log(f"Found: {device.name} ({device.address})")
                return device
        
        return None
    
    def handle_sensor_notification(self, sender: int, data: bytearray):
        """Handle incoming sensor data"""
        self.packet_count += 1
        timestamp = datetime.datetime.now()
        
        # First packet - streaming confirmed
        if not self.is_streaming:
            self.is_streaming = True
            self.session_start = timestamp
            self.log("Streaming started!")
            
            # Initialize raw stream file
            if self.save_raw:
                filename = f"{self.data_dir}/muse_{timestamp.strftime('%Y%m%d_%H%M%S')}.bin"
                self.raw_stream = MuseRawStream(filename)
                self.raw_stream.open_write()
                self.log(f"Saving to: {filename}")
        
        # Save raw data
        if self.save_raw and self.raw_stream:
            self.raw_stream.write_packet(bytes(data), timestamp)
        
        # Decode in real-time
        if self.decode_realtime and self.decoder:
            decoded = self.decoder.decode(bytes(data), timestamp)
        
        # User callback for raw packets
        if self.user_callbacks['packet']:
            self.user_callbacks['packet'](bytes(data))
        
        # Status update every 100 packets
        if self.packet_count % 100 == 0:
            self.log(f"Packets: {self.packet_count}")
            if self.decoder:
                stats = self.decoder.get_stats()
                if stats['last_heart_rate']:
                    self.log(f"Heart Rate: {stats['last_heart_rate']:.0f} BPM")
    
    def handle_control_notification(self, sender: int, data: bytearray):
        """Handle control responses"""
        try:
            # Try to decode as string/JSON
            text = data.decode('utf-8', errors='ignore')
            if '{' in text and '}' in text:
                # Extract JSON portion
                start = text.index('{')
                end = text.rindex('}') + 1
                json_str = text[start:end]
                
                import json
                info = json.loads(json_str)
                self.device_info.update(info)
                
                if self.verbose:
                    if 'fw' in info:
                        self.log(f"Firmware: {info['fw']}")
                    if 'bp' in info:
                        self.log(f"Battery: {info['bp']}%")
        except:
            pass
    
    async def connect_and_stream(self, 
                                 address: str,
                                 duration_seconds: int = 30,
                                 preset: str = 'p1034') -> bool:
        """
        Connect and stream data
        
        Args:
            address: Device MAC address
            duration_seconds: Streaming duration (0 for continuous)
            preset: Sensor preset ('p21' for basic, 'p1034' for full)
            
        Returns:
            Success status
        """
        try:
            self.log(f"Connecting to {address}...")
            
            async with BleakClient(address) as client:
                self.client = client
                self.log("Connected!")
                
                # Enable control notifications
                await client.start_notify(CONTROL_CHAR_UUID, self.handle_control_notification)
                
                # Get device info
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['v6'], response=False)
                await asyncio.sleep(0.1)
                
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['s'], response=False)
                await asyncio.sleep(0.1)
                
                # Halt any existing streams
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['h'], response=False)
                await asyncio.sleep(0.1)
                
                # Set preset
                self.log(f"Setting preset: {preset}")
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS[preset], response=False)
                await asyncio.sleep(0.1)
                
                # Enable sensor notifications
                sensor_enabled = False
                for char_uuid in SENSOR_CHAR_UUIDS:
                    try:
                        await client.start_notify(char_uuid, self.handle_sensor_notification)
                        sensor_enabled = True
                        self.log(f"Sensor notifications enabled")
                        break
                    except:
                        continue
                
                if not sensor_enabled:
                    self.log("Failed to enable sensor notifications")
                    return False
                
                # Start streaming (SEND TWICE!)
                self.log("Starting stream...")
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'], response=False)
                await asyncio.sleep(0.05)
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'], response=False)
                await asyncio.sleep(0.1)
                
                # Send L1 command
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['L1'], response=False)
                
                # Wait for streaming to start
                await asyncio.sleep(2)
                
                if not self.is_streaming:
                    self.log("Streaming failed to start")
                    return False
                
                # Stream for specified duration
                if duration_seconds > 0:
                    self.log(f"Streaming for {duration_seconds} seconds...")
                    await asyncio.sleep(duration_seconds)
                else:
                    self.log("Streaming continuously (Ctrl+C to stop)...")
                    while True:
                        await asyncio.sleep(1)
                
                # Stop streaming
                self.log("Stopping stream...")
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['h'], response=False)
                
                return True
                
        except Exception as e:
            self.log(f"Error: {e}")
            return False
        
        finally:
            # Clean up
            if self.raw_stream:
                self.raw_stream.close()
                if self.verbose:
                    info = self.raw_stream.get_file_info()
                    self.log(f"Saved {info['packet_count']} packets ({info['file_size_mb']:.1f} MB)")
            
            self.client = None
    
    def get_summary(self) -> Dict[str, Any]:
        """Get session summary"""
        summary = {
            'packets_received': self.packet_count,
            'session_start': self.session_start,
            'device_info': self.device_info
        }
        
        if self.decoder:
            stats = self.decoder.get_stats()
            summary.update({
                'eeg_samples': stats['eeg_samples'],
                'ppg_samples': stats['ppg_samples'],
                'imu_samples': stats['imu_samples'],
                'last_heart_rate': stats['last_heart_rate'],
                'decode_errors': stats['decode_errors']
            })
        
        if self.raw_stream:
            info = self.raw_stream.get_file_info()
            summary['file_info'] = info
        
        return summary

# Convenience functions
async def stream_only(duration_seconds: int = 30, preset: str = 'p1034'):
    """
    Stream data without saving (real-time processing only)
    
    Args:
        duration_seconds: How long to stream
        preset: Sensor configuration
    """
    client = MuseStreamClient(save_raw=False, decode_realtime=True)
    
    # Find device
    device = await client.find_device()
    if not device:
        print("No Muse device found")
        return None
    
    # Stream without saving
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=duration_seconds,
        preset=preset
    )
    
    if success:
        summary = client.get_summary()
        print(f"\nSession complete!")
        print(f"Packets: {summary['packets_received']}")
        if 'eeg_samples' in summary:
            print(f"EEG samples: {summary['eeg_samples']}")
        if 'last_heart_rate' in summary and summary['last_heart_rate']:
            print(f"Last heart rate: {summary['last_heart_rate']:.0f} BPM")
        return summary
    
    return None

async def stream_and_save(duration_seconds: int = 30, preset: str = 'p1034'):
    """
    Stream AND save data to binary file
    
    Args:
        duration_seconds: How long to stream
        preset: Sensor configuration
    """
    client = MuseStreamClient(save_raw=True, decode_realtime=True)
    
    # Find device
    device = await client.find_device()
    if not device:
        print("No Muse device found")
        return None
    
    # Stream and save
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=duration_seconds,
        preset=preset
    )
    
    if success:
        summary = client.get_summary()
        print(f"\nSession complete!")
        print(f"Packets: {summary['packets_received']}")
        if 'file_info' in summary:
            print(f"Saved to: {summary['file_info']['filepath']}")
            print(f"File size: {summary['file_info']['file_size_mb']:.1f} MB")
        return summary
    
    return None

# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def example():
        """Example with callbacks"""
        client = MuseStreamClient()
        
        # Register callbacks
        client.on_eeg(lambda data: print(f"EEG: {len(data['channels'])} channels"))
        client.on_heart_rate(lambda hr: print(f"Heart Rate: {hr:.0f} BPM"))
        
        # Find and connect
        device = await client.find_device()
        if device:
            await client.connect_and_stream(device.address, duration_seconds=30)
            
            # Show summary
            summary = client.get_summary()
            print(f"\nSummary: {summary}")
    
    # Run example
    asyncio.run(example())