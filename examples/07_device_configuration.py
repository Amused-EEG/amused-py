"""
Example 7: Device Configuration and Discovery
Demonstrates programmatic use of the device configuration system

Features:
- Automatic device discovery
- Configuration persistence
- Preferred device selection
- Custom buffer sizes
- Quick connection
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_config import MuseDeviceConfig, MuseDevice
from muse_stream_client import MuseStreamClient
from muse_visualizer import MuseVisualizer


async def example_device_discovery():
    """Example: Discover and save Muse devices"""
    print("=" * 60)
    print("Example 1: Device Discovery")
    print("=" * 60)
    
    # Create config manager
    config = MuseDeviceConfig()
    
    # Scan for devices
    print("\nScanning for Muse devices...")
    devices = await config.scan_for_devices(timeout=5.0)
    
    if not devices:
        print("No Muse devices found")
        print("\nTroubleshooting:")
        print("1. Ensure your Muse is powered on")
        print("2. Hold the power button for pairing mode")
        print("3. Check Bluetooth is enabled")
        return None
    
    # Display found devices
    print(f"\nFound {len(devices)} device(s):")
    for i, device in enumerate(devices, 1):
        signal_strength = "Strong" if device.rssi > -60 else "Medium" if device.rssi > -75 else "Weak"
        print(f"\n{i}. {device.name}")
        print(f"   Model: {device.model}")
        print(f"   Address: {device.address}")
        print(f"   Signal: {signal_strength} ({device.rssi} dBm)")
    
    # Set first device as preferred
    if len(devices) == 1:
        config.set_preferred_device(devices[0].address)
        print(f"\nAutomatically set {devices[0].name} as preferred device")
    elif len(devices) > 1:
        print("\nMultiple devices found. Which would you like to use?")
        try:
            choice = int(input(f"Enter device number (1-{len(devices)}): "))
            if 1 <= choice <= len(devices):
                selected = devices[choice - 1]
                config.set_preferred_device(selected.address)
                print(f"Set {selected.name} as preferred device")
        except:
            print("Using first device")
            config.set_preferred_device(devices[0].address)
    
    return config


async def example_custom_buffers():
    """Example: Configure custom buffer sizes for visualization"""
    print("\n" + "=" * 60)
    print("Example 2: Custom Buffer Configuration")
    print("=" * 60)
    
    config = MuseDeviceConfig()
    
    # Show current settings
    print("\nCurrent buffer sizes:")
    print(f"  EEG: {config.get_buffer_size('eeg_window')} samples ({config.get_buffer_size('eeg_window')/256:.1f} seconds)")
    print(f"  PPG: {config.get_buffer_size('ppg_window')} samples ({config.get_buffer_size('ppg_window')/64:.1f} seconds)")
    print(f"  IMU: {config.get_buffer_size('imu_window')} samples ({config.get_buffer_size('imu_window')/52:.1f} seconds)")
    
    # Set custom sizes
    print("\nSetting custom buffer sizes...")
    
    # Set to 5 seconds of data
    config.set_buffer_size('eeg_window', 1280)  # 5 seconds at 256 Hz
    config.set_buffer_size('ppg_window', 320)   # 5 seconds at 64 Hz
    config.set_buffer_size('imu_window', 260)   # 5 seconds at 52 Hz
    
    print("\nNew buffer sizes:")
    print(f"  EEG: {config.get_buffer_size('eeg_window')} samples (5.0 seconds)")
    print(f"  PPG: {config.get_buffer_size('ppg_window')} samples (5.0 seconds)")
    print(f"  IMU: {config.get_buffer_size('imu_window')} samples (5.0 seconds)")
    
    return config


async def example_quick_connect():
    """Example: Quick connection using saved configuration"""
    print("\n" + "=" * 60)
    print("Example 3: Quick Connect")
    print("=" * 60)
    
    config = MuseDeviceConfig()
    
    # Check for preferred device
    preferred = config.get_preferred_device()
    if preferred:
        print(f"\nUsing preferred device: {preferred.name}")
    else:
        print("\nNo preferred device set. Will scan for devices...")
    
    # Quick connect (uses preferred device or scans)
    result = await config.quick_connect()
    
    if not result:
        print("Failed to connect to any device")
        return None
    
    device, client = result
    print(f"\n✓ Connected to {device.name}")
    print(f"  Model: {device.model}")
    print(f"  Address: {device.address}")
    
    # Do something with the connection
    print("\nDevice is ready for streaming!")
    await asyncio.sleep(2)
    
    # Disconnect
    await client.disconnect()
    print("✓ Disconnected")
    
    return device


async def example_integrated_streaming():
    """Example: Stream with configuration-based setup"""
    print("\n" + "=" * 60)
    print("Example 4: Integrated Streaming with Config")
    print("=" * 60)
    
    # Load configuration
    config = MuseDeviceConfig()
    
    # Create stream client
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=True
    )
    
    # Find device using config system
    print("\nFinding device using configuration...")
    device = await client.find_device(use_config=True)
    
    if not device:
        print("No device found")
        return
    
    print(f"Found: {device.name}")
    
    # Create visualizer with config buffer sizes
    print("\nInitializing visualizer with configured buffer sizes...")
    viz = MuseVisualizer(
        backend='auto',
        use_config=True  # This loads buffer sizes from config
    )
    
    # Show what buffer sizes are being used
    eeg_buffer = config.get_buffer_size('eeg_window')
    print(f"  EEG buffer: {eeg_buffer} samples ({eeg_buffer/256:.1f} seconds)")
    
    # Register visualization callbacks
    client.on_eeg(viz.update_eeg)
    client.on_ppg(viz.update_ppg)
    client.on_heart_rate(viz.update_heart_rate)
    client.on_imu(viz.update_imu)
    
    print("\nStarting 30-second streaming session...")
    
    # Stream for 30 seconds
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=30,
        preset='p1034'  # Full sensor suite
    )
    
    if success:
        print("\n✓ Streaming completed successfully")
        summary = client.get_summary()
        print(f"  Total packets: {summary['packets_received']}")
        print(f"  EEG packets: {summary['eeg_packets']}")
        print(f"  PPG packets: {summary['ppg_packets']}")
    else:
        print("\n✗ Streaming failed")


async def example_manual_device_management():
    """Example: Manual device management"""
    print("\n" + "=" * 60)
    print("Example 5: Manual Device Management")
    print("=" * 60)
    
    config = MuseDeviceConfig()
    
    # List all known devices
    devices = config.list_devices()
    print(f"\nCurrently know {len(devices)} device(s)")
    
    for device in devices:
        print(f"\n- {device.name}")
        print(f"  Address: {device.address}")
        print(f"  Model: {device.model}")
        print(f"  Last seen: {device.last_seen}")
        print(f"  Preferred: {device.preferred}")
    
    # You can also manually add a device if you know its details
    manual_device = MuseDevice(
        name="Muse S (Manual)",
        address="00:11:22:33:44:55",  # Example MAC
        rssi=-70,
        model="Muse S",
        preferred=False
    )
    
    # Add to config (uncomment to actually add)
    # config.devices[manual_device.address] = manual_device
    # config.save_config()
    # print(f"\nAdded manual device: {manual_device.name}")
    
    # Remove a device (uncomment to remove)
    # if devices:
    #     config.remove_device(devices[0].address)
    #     print(f"Removed device: {devices[0].name}")
    
    return config


async def main():
    """Main example runner"""
    print("Amused Device Configuration Examples")
    print("=" * 60)
    print("\nThis example demonstrates programmatic device configuration")
    print("The configuration is saved in ~/.amused/devices.json")
    print()
    
    examples = [
        ("Device Discovery", example_device_discovery),
        ("Custom Buffers", example_custom_buffers),
        ("Quick Connect", example_quick_connect),
        ("Integrated Streaming", example_integrated_streaming),
        ("Manual Management", example_manual_device_management),
    ]
    
    print("Available examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"{i}. {name}")
    print("0. Run all examples")
    
    try:
        choice = input("\nSelect example (0-5): ")
        choice = int(choice)
        
        if choice == 0:
            # Run all examples
            for name, func in examples:
                print(f"\n{'='*60}")
                print(f"Running: {name}")
                print('='*60)
                await func()
                await asyncio.sleep(1)
        elif 1 <= choice <= len(examples):
            # Run selected example
            name, func = examples[choice - 1]
            await func()
        else:
            print("Invalid choice")
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Windows event loop fix
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())