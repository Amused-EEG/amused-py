"""
Amused Configuration Helper
High-level convenience functions for device configuration
"""

import asyncio
from typing import Optional, Dict, Any
from muse_config import MuseDeviceConfig, MuseDevice
from muse_stream_client import MuseStreamClient


class AmusedConfig:
    """
    High-level configuration interface for Amused
    
    This class provides simple methods for common configuration tasks
    without needing to understand the underlying configuration system.
    """
    
    def __init__(self):
        """Initialize configuration helper"""
        self.config = MuseDeviceConfig()
    
    async def auto_setup(self) -> Optional[MuseDevice]:
        """
        Automatically setup Muse device
        
        This will:
        1. Check for preferred device
        2. If none, scan for devices
        3. If found, set first as preferred
        4. Return the device to use
        
        Returns:
            MuseDevice or None if no device found
        """
        # Check for existing preferred device
        device = self.config.get_preferred_device()
        if device:
            print(f"Using preferred device: {device.name}")
            return device
        
        # Scan for new devices
        print("No preferred device set. Scanning...")
        devices = await self.config.scan_for_devices()
        
        if not devices:
            print("No Muse devices found")
            return None
        
        # Use first device found
        device = devices[0]
        self.config.set_preferred_device(device.address)
        print(f"Found and set {device.name} as preferred device")
        
        return device
    
    def set_visualization_time(self, seconds: float):
        """
        Set visualization buffer to show N seconds of data
        
        Args:
            seconds: Number of seconds to show in visualization
        """
        # Calculate samples for each sensor
        eeg_samples = int(seconds * 256)  # 256 Hz
        ppg_samples = int(seconds * 64)   # 64 Hz
        imu_samples = int(seconds * 52)   # 52 Hz
        
        # Set buffer sizes
        self.config.set_buffer_size('eeg_window', eeg_samples)
        self.config.set_buffer_size('ppg_window', ppg_samples)
        self.config.set_buffer_size('imu_window', imu_samples)
        
        print(f"Set visualization buffers to {seconds} seconds")
    
    def get_visualization_time(self) -> float:
        """
        Get current visualization time window in seconds
        
        Returns:
            Time window in seconds
        """
        eeg_samples = self.config.get_buffer_size('eeg_window')
        return eeg_samples / 256.0
    
    async def create_configured_client(self, **kwargs) -> MuseStreamClient:
        """
        Create a stream client with configuration
        
        Args:
            **kwargs: Additional arguments for MuseStreamClient
            
        Returns:
            Configured MuseStreamClient
        """
        # Default settings
        defaults = {
            'save_raw': False,
            'decode_realtime': True,
            'verbose': True
        }
        defaults.update(kwargs)
        
        # Create client
        client = MuseStreamClient(**defaults)
        
        # Client will use config system by default
        return client
    
    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        # Reset buffer sizes
        for buffer_type, size in MuseDeviceConfig.DEFAULT_BUFFER_SIZES.items():
            self.config.set_buffer_size(buffer_type, size)
        
        # Clear preferred device
        for device in self.config.devices.values():
            device.preferred = False
        
        self.config.save_config()
        print("Configuration reset to defaults")
    
    def show_config(self) -> Dict[str, Any]:
        """
        Get current configuration as dictionary
        
        Returns:
            Configuration dictionary
        """
        devices = []
        for device in self.config.devices.values():
            devices.append({
                'name': device.name,
                'address': device.address,
                'model': device.model,
                'preferred': device.preferred
            })
        
        buffer_times = {
            'eeg': self.config.get_buffer_size('eeg_window') / 256.0,
            'ppg': self.config.get_buffer_size('ppg_window') / 64.0,
            'imu': self.config.get_buffer_size('imu_window') / 52.0,
        }
        
        return {
            'devices': devices,
            'buffer_sizes': self.config.settings['buffer_sizes'],
            'buffer_times_seconds': buffer_times,
            'auto_connect': self.config.settings.get('auto_connect', True),
            'config_file': self.config.config_file
        }


# Convenience functions for quick access
_global_config = None

def get_config() -> AmusedConfig:
    """Get global configuration instance"""
    global _global_config
    if _global_config is None:
        _global_config = AmusedConfig()
    return _global_config


async def quick_setup() -> Optional[MuseDevice]:
    """
    Quick setup for Muse device
    
    Returns:
        MuseDevice or None
        
    Example:
        import amused.amused_config as aconfig
        device = await aconfig.quick_setup()
        if device:
            print(f"Ready to connect to {device.name}")
    """
    config = get_config()
    return await config.auto_setup()


def set_viz_time(seconds: float):
    """
    Set visualization time window
    
    Args:
        seconds: Time window in seconds
        
    Example:
        import amused.amused_config as aconfig
        aconfig.set_viz_time(5.0)  # Show 5 seconds of data
    """
    config = get_config()
    config.set_visualization_time(seconds)


def show_settings():
    """
    Print current configuration
    
    Example:
        import amused.amused_config as aconfig
        aconfig.show_settings()
    """
    config = get_config()
    settings = config.show_config()
    
    print("\nAmused Configuration")
    print("=" * 50)
    
    print("\nDevices:")
    if settings['devices']:
        for dev in settings['devices']:
            pref = " [PREFERRED]" if dev['preferred'] else ""
            print(f"  - {dev['name']} ({dev['model']}){pref}")
            print(f"    Address: {dev['address']}")
    else:
        print("  No devices configured")
    
    print("\nVisualization buffers:")
    for sensor, time in settings['buffer_times_seconds'].items():
        print(f"  {sensor.upper()}: {time:.1f} seconds")
    
    print(f"\nAuto-connect: {settings['auto_connect']}")
    print(f"Config file: {settings['config_file']}")


if __name__ == "__main__":
    # Test the configuration helper
    async def test():
        print("Testing Amused Configuration Helper")
        print("=" * 50)
        
        # Show current settings
        show_settings()
        
        # Set visualization to 5 seconds
        set_viz_time(5.0)
        
        # Quick setup
        device = await quick_setup()
        if device:
            print(f"\nDevice ready: {device.name}")
        
        # Show updated settings
        print("\nUpdated configuration:")
        show_settings()
    
    asyncio.run(test())