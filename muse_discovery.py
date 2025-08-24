"""
Muse Device Discovery
Simple Bluetooth device discovery for Muse headsets
"""

import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from bleak import BleakScanner, BleakClient


@dataclass
class MuseDevice:
    """Simple Muse device representation"""
    name: str
    address: str
    rssi: int = -100
    
    def __str__(self):
        """String representation"""
        signal = "Strong" if self.rssi > -60 else "Medium" if self.rssi > -75 else "Weak"
        return f"{self.name} ({self.address}) - Signal: {signal}"


async def find_muse_devices(timeout: float = 5.0) -> List[MuseDevice]:
    """
    Scan for nearby Muse devices
    
    Args:
        timeout: Scan timeout in seconds
        
    Returns:
        List of discovered Muse devices
        
    Example:
        devices = await find_muse_devices()
        for device in devices:
            print(device)
    """
    print(f"Scanning for Muse devices ({timeout}s)...")
    
    devices = []
    try:
        discovered = await BleakScanner.discover(timeout=timeout)
        
        for device in discovered:
            # Check if it's a Muse device
            if device.name and "Muse" in device.name:
                muse = MuseDevice(
                    name=device.name,
                    address=device.address,
                    rssi=getattr(device, 'rssi', -100)
                )
                devices.append(muse)
                print(f"  Found: {muse}")
    
    except Exception as e:
        print(f"Scan error: {e}")
    
    if not devices:
        print("No Muse devices found")
    
    return devices


async def select_device(devices: Optional[List[MuseDevice]] = None) -> Optional[MuseDevice]:
    """
    Select a Muse device interactively
    
    Args:
        devices: List of devices to choose from (will scan if None)
        
    Returns:
        Selected MuseDevice or None
        
    Example:
        device = await select_device()
        if device:
            print(f"Selected: {device.name}")
    """
    # Scan if no devices provided
    if devices is None:
        devices = await find_muse_devices()
    
    if not devices:
        return None
    
    # Auto-select if only one device
    if len(devices) == 1:
        print(f"Auto-selecting: {devices[0].name}")
        return devices[0]
    
    # Show options
    print("\nMultiple devices found:")
    for i, device in enumerate(devices, 1):
        print(f"{i}. {device}")
    
    # Get user choice
    while True:
        try:
            choice = input(f"\nSelect device (1-{len(devices)}) or 'q' to quit: ")
            if choice.lower() == 'q':
                return None
            
            idx = int(choice) - 1
            if 0 <= idx < len(devices):
                return devices[idx]
        except (ValueError, IndexError):
            print("Invalid selection")


async def connect_to_address(address: str, timeout: float = 10.0) -> Optional[BleakClient]:
    """
    Connect directly to a device by MAC address
    
    Args:
        address: Bluetooth MAC address
        timeout: Connection timeout in seconds
        
    Returns:
        Connected BleakClient or None
        
    Example:
        client = await connect_to_address("XX:XX:XX:XX:XX:XX")
        if client and client.is_connected:
            print("Connected!")
    """
    print(f"Connecting to {address}...")
    
    try:
        client = BleakClient(address, timeout=timeout)
        await client.connect()
        
        if client.is_connected:
            print(f"Connected to {address}")
            return client
        else:
            print(f"Failed to connect to {address}")
            return None
            
    except Exception as e:
        print(f"Connection error: {e}")
        return None


async def quick_connect(name_filter: str = "Muse") -> Optional[tuple[MuseDevice, BleakClient]]:
    """
    Quick connect to first available Muse device
    
    Args:
        name_filter: Filter for device name
        
    Returns:
        Tuple of (MuseDevice, BleakClient) or None
        
    Example:
        result = await quick_connect()
        if result:
            device, client = result
            print(f"Connected to {device.name}")
            # Use client...
            await client.disconnect()
    """
    # Find devices
    devices = await find_muse_devices()
    
    # Filter by name if specified
    if name_filter:
        devices = [d for d in devices if name_filter in d.name]
    
    if not devices:
        print(f"No devices matching '{name_filter}' found")
        return None
    
    # Use first device
    device = devices[0]
    print(f"Connecting to {device.name}...")
    
    # Connect
    client = await connect_to_address(device.address)
    if client:
        return device, client
    
    return None


# Simple test/demo
if __name__ == "__main__":
    async def demo():
        print("Muse Device Discovery Demo")
        print("=" * 40)
        
        # Find all devices
        devices = await find_muse_devices()
        
        if devices:
            # Select one
            selected = await select_device(devices)
            if selected:
                print(f"\nYou selected: {selected.name}")
                print(f"Address: {selected.address}")
                
                # Try to connect
                client = await connect_to_address(selected.address)
                if client:
                    print("Successfully connected!")
                    await asyncio.sleep(1)
                    await client.disconnect()
                    print("Disconnected")
    
    asyncio.run(demo())