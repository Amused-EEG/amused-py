"""
Muse Device Configuration and Discovery
Handles device discovery, configuration storage, and connection management

Features:
- Automatic device discovery
- Configuration persistence
- Multiple device support
- Connection preferences
"""

import json
import os
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import bleak
from bleak import BleakScanner, BleakClient

@dataclass
class MuseDevice:
    """Muse device information"""
    name: str
    address: str
    rssi: int
    model: str = "Unknown"
    last_seen: str = ""
    preferred: bool = False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'MuseDevice':
        """Create from dictionary"""
        return cls(**data)


class MuseDeviceConfig:
    """
    Manages Muse device discovery and configuration
    
    Features:
    - Scan for nearby Muse devices
    - Save/load device configurations
    - Set preferred device
    - Quick connect to known devices
    """
    
    CONFIG_FILE = os.path.expanduser("~/.amused/devices.json")
    MUSE_NAME_PREFIXES = ["Muse", "MUSE"]
    
    # Visualization settings with sensible defaults
    DEFAULT_BUFFER_SIZES = {
        'eeg_window': 2560,      # 10 seconds at 256 Hz
        'ppg_window': 640,       # 10 seconds at 64 Hz  
        'imu_window': 520,       # 10 seconds at 52 Hz
        'heart_rate_window': 120 # 2 minutes of HR values
    }
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize configuration manager
        
        Args:
            config_file: Optional custom config file path
        """
        self.config_file = config_file or self.CONFIG_FILE
        self.devices: Dict[str, MuseDevice] = {}
        self.settings: Dict = {
            'buffer_sizes': self.DEFAULT_BUFFER_SIZES.copy(),
            'auto_connect': True,
            'scan_timeout': 5.0,
            'connection_timeout': 10.0
        }
        
        # Ensure config directory exists
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        
        # Load existing configuration
        self.load_config()
    
    def load_config(self) -> bool:
        """
        Load configuration from file
        
        Returns:
            True if config loaded successfully
        """
        if not os.path.exists(self.config_file):
            return False
        
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
                
            # Load devices
            for address, device_data in data.get('devices', {}).items():
                self.devices[address] = MuseDevice.from_dict(device_data)
            
            # Load settings
            self.settings.update(data.get('settings', {}))
            
            return True
        except Exception as e:
            print(f"Error loading config: {e}")
            return False
    
    def save_config(self) -> bool:
        """
        Save configuration to file
        
        Returns:
            True if saved successfully
        """
        try:
            data = {
                'devices': {addr: dev.to_dict() for addr, dev in self.devices.items()},
                'settings': self.settings,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    async def scan_for_devices(self, timeout: float = None) -> List[MuseDevice]:
        """
        Scan for nearby Muse devices
        
        Args:
            timeout: Scan timeout in seconds
            
        Returns:
            List of discovered Muse devices
        """
        timeout = timeout or self.settings['scan_timeout']
        discovered = []
        
        print(f"Scanning for Muse devices for {timeout} seconds...")
        
        try:
            devices = await BleakScanner.discover(timeout=timeout)
            
            for device in devices:
                # Check if it's a Muse device
                if device.name and any(device.name.startswith(prefix) for prefix in self.MUSE_NAME_PREFIXES):
                    # Determine model from name
                    model = "Unknown"
                    if "Muse S" in device.name or "Muse-S" in device.name:
                        model = "Muse S"
                    elif "Muse 2" in device.name:
                        model = "Muse 2"
                    elif "Muse" in device.name:
                        model = "Muse (Original)"
                    
                    muse_device = MuseDevice(
                        name=device.name,
                        address=device.address,
                        rssi=device.rssi if hasattr(device, 'rssi') else -100,
                        model=model,
                        last_seen=datetime.now().isoformat()
                    )
                    
                    # Check if we've seen this device before
                    if device.address in self.devices:
                        muse_device.preferred = self.devices[device.address].preferred
                    
                    discovered.append(muse_device)
                    self.devices[device.address] = muse_device
            
            # Save updated device list
            self.save_config()
            
        except Exception as e:
            print(f"Error during scan: {e}")
        
        return discovered
    
    def set_preferred_device(self, address: str) -> bool:
        """
        Set a device as preferred for auto-connect
        
        Args:
            address: Device MAC address
            
        Returns:
            True if device was set as preferred
        """
        if address not in self.devices:
            return False
        
        # Clear other preferred flags
        for device in self.devices.values():
            device.preferred = False
        
        # Set this device as preferred
        self.devices[address].preferred = True
        self.save_config()
        
        return True
    
    def get_preferred_device(self) -> Optional[MuseDevice]:
        """
        Get the preferred device for auto-connect
        
        Returns:
            Preferred MuseDevice or None
        """
        for device in self.devices.values():
            if device.preferred:
                return device
        return None
    
    def get_buffer_size(self, buffer_type: str) -> int:
        """
        Get configured buffer size for visualization
        
        Args:
            buffer_type: Type of buffer (eeg_window, ppg_window, etc.)
            
        Returns:
            Buffer size in samples
        """
        return self.settings['buffer_sizes'].get(buffer_type, 1000)
    
    def set_buffer_size(self, buffer_type: str, size: int) -> bool:
        """
        Set buffer size for visualization
        
        Args:
            buffer_type: Type of buffer
            size: Size in samples
            
        Returns:
            True if set successfully
        """
        if size < 100 or size > 10000:
            print(f"Buffer size must be between 100 and 10000 samples")
            return False
        
        self.settings['buffer_sizes'][buffer_type] = size
        self.save_config()
        return True
    
    async def find_device(self, preferred_only: bool = False) -> Optional[MuseDevice]:
        """
        Find a Muse device to connect to
        
        Args:
            preferred_only: Only return preferred device
            
        Returns:
            MuseDevice to connect to or None
        """
        # First check for preferred device
        if self.settings.get('auto_connect', True):
            preferred = self.get_preferred_device()
            if preferred:
                print(f"Using preferred device: {preferred.name} ({preferred.address})")
                return preferred
        
        if preferred_only:
            return None
        
        # Scan for new devices
        devices = await self.scan_for_devices()
        
        if not devices:
            print("No Muse devices found")
            return None
        
        # If only one device, use it
        if len(devices) == 1:
            return devices[0]
        
        # Let user choose
        print("\nMultiple Muse devices found:")
        for i, device in enumerate(devices):
            signal = "Strong" if device.rssi > -60 else "Medium" if device.rssi > -75 else "Weak"
            print(f"{i+1}. {device.name} - {device.model} ({device.address}) - Signal: {signal}")
        
        while True:
            try:
                choice = input("\nSelect device (1-{}) or 'q' to quit: ".format(len(devices)))
                if choice.lower() == 'q':
                    return None
                idx = int(choice) - 1
                if 0 <= idx < len(devices):
                    selected = devices[idx]
                    # Ask if should be set as preferred
                    if input("Set as preferred device? (y/n): ").lower() == 'y':
                        self.set_preferred_device(selected.address)
                    return selected
            except (ValueError, IndexError):
                print("Invalid selection")
    
    async def quick_connect(self) -> Optional[Tuple[MuseDevice, BleakClient]]:
        """
        Quickly connect to a Muse device
        
        Returns:
            Tuple of (MuseDevice, BleakClient) or None
        """
        device = await self.find_device()
        if not device:
            return None
        
        print(f"Connecting to {device.name}...")
        
        try:
            client = BleakClient(
                device.address,
                timeout=self.settings.get('connection_timeout', 10.0)
            )
            await client.connect()
            
            if client.is_connected:
                print(f"Connected to {device.name}")
                return device, client
            else:
                print(f"Failed to connect to {device.name}")
                return None
                
        except Exception as e:
            print(f"Connection error: {e}")
            return None
    
    def list_devices(self) -> List[MuseDevice]:
        """
        List all known devices
        
        Returns:
            List of known MuseDevice objects
        """
        return list(self.devices.values())
    
    def remove_device(self, address: str) -> bool:
        """
        Remove a device from configuration
        
        Args:
            address: Device MAC address
            
        Returns:
            True if device was removed
        """
        if address in self.devices:
            del self.devices[address]
            self.save_config()
            return True
        return False


async def interactive_setup():
    """Interactive device setup and configuration"""
    config = MuseDeviceConfig()
    
    print("=" * 60)
    print("Amused - Muse Device Configuration")
    print("=" * 60)
    
    while True:
        print("\nOptions:")
        print("1. Scan for devices")
        print("2. List known devices")
        print("3. Set preferred device")
        print("4. Configure buffer sizes")
        print("5. Test connection")
        print("6. Remove device")
        print("0. Exit")
        
        choice = input("\nSelect option: ")
        
        if choice == '0':
            break
        
        elif choice == '1':
            devices = await config.scan_for_devices()
            if devices:
                print(f"\nFound {len(devices)} device(s):")
                for dev in devices:
                    print(f"  - {dev.name} ({dev.model}) - {dev.address}")
            else:
                print("No devices found")
        
        elif choice == '2':
            devices = config.list_devices()
            if devices:
                print(f"\nKnown devices:")
                for dev in devices:
                    pref = " [PREFERRED]" if dev.preferred else ""
                    print(f"  - {dev.name} ({dev.model}) - {dev.address}{pref}")
                    print(f"    Last seen: {dev.last_seen}")
            else:
                print("No known devices")
        
        elif choice == '3':
            devices = config.list_devices()
            if not devices:
                print("No known devices. Scan first.")
                continue
            
            print("\nSelect device to set as preferred:")
            for i, dev in enumerate(devices):
                print(f"{i+1}. {dev.name} - {dev.address}")
            
            try:
                idx = int(input("Device number: ")) - 1
                if 0 <= idx < len(devices):
                    config.set_preferred_device(devices[idx].address)
                    print(f"Set {devices[idx].name} as preferred")
            except:
                print("Invalid selection")
        
        elif choice == '4':
            print("\nBuffer sizes (samples):")
            print(f"1. EEG window: {config.get_buffer_size('eeg_window')} (256 Hz)")
            print(f"2. PPG window: {config.get_buffer_size('ppg_window')} (64 Hz)")
            print(f"3. IMU window: {config.get_buffer_size('imu_window')} (52 Hz)")
            print(f"4. Heart rate window: {config.get_buffer_size('heart_rate_window')} points")
            
            buffer_type = input("\nSelect buffer to configure (1-4): ")
            types = {'1': 'eeg_window', '2': 'ppg_window', '3': 'imu_window', '4': 'heart_rate_window'}
            
            if buffer_type in types:
                try:
                    size = int(input("New size (100-10000): "))
                    if config.set_buffer_size(types[buffer_type], size):
                        print("Buffer size updated")
                except:
                    print("Invalid size")
        
        elif choice == '5':
            result = await config.quick_connect()
            if result:
                device, client = result
                print(f"Successfully connected to {device.name}")
                await client.disconnect()
                print("Disconnected")
        
        elif choice == '6':
            devices = config.list_devices()
            if not devices:
                print("No devices to remove")
                continue
            
            print("\nSelect device to remove:")
            for i, dev in enumerate(devices):
                print(f"{i+1}. {dev.name} - {dev.address}")
            
            try:
                idx = int(input("Device number: ")) - 1
                if 0 <= idx < len(devices):
                    config.remove_device(devices[idx].address)
                    print(f"Removed {devices[idx].name}")
            except:
                print("Invalid selection")
    
    print("\nConfiguration saved!")


if __name__ == "__main__":
    # Run interactive setup
    asyncio.run(interactive_setup())