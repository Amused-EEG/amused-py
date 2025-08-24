"""
Example 8: Simple Device Discovery and Connection
Shows the clean, minimal approach to finding and connecting to Muse devices

No configuration files, no persistence - just simple device discovery
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_discovery import find_muse_devices, select_device, connect_to_address
from muse_stream_client import MuseStreamClient


async def example_basic_discovery():
    """Example: Basic device discovery"""
    print("=" * 60)
    print("Basic Device Discovery")
    print("=" * 60)
    
    # Find all Muse devices
    devices = await find_muse_devices(timeout=5.0)
    
    if not devices:
        print("\nNo Muse devices found!")
        print("Make sure your Muse is:")
        print("- Powered on")
        print("- In pairing mode") 
        print("- Bluetooth is enabled")
        return None
    
    # Display what we found
    print(f"\nFound {len(devices)} device(s):")
    for device in devices:
        print(f"  {device}")
    
    return devices


async def example_device_selection():
    """Example: Interactive device selection"""
    print("\n" + "=" * 60)
    print("Device Selection")
    print("=" * 60)
    
    # Let user select a device
    device = await select_device()
    
    if device:
        print(f"\nYou selected: {device.name}")
        print(f"MAC Address: {device.address}")
        return device
    else:
        print("\nNo device selected")
        return None


async def example_direct_connection():
    """Example: Direct connection by MAC address"""
    print("\n" + "=" * 60)
    print("Direct Connection")
    print("=" * 60)
    
    # If you know the MAC address, connect directly
    # Replace with your device's actual MAC address
    mac_address = "XX:XX:XX:XX:XX:XX"
    
    print(f"\nTo connect directly, use a known MAC address:")
    print(f"  mac_address = '{mac_address}'")
    print(f"  client = await connect_to_address(mac_address)")
    
    # Uncomment to actually try connecting:
    # client = await connect_to_address(mac_address)
    # if client:
    #     print("Connected!")
    #     await client.disconnect()


async def example_streaming_simple():
    """Example: Simple streaming with device discovery"""
    print("\n" + "=" * 60)
    print("Simple Streaming")
    print("=" * 60)
    
    # Create stream client
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=True
    )
    
    # Find a device
    print("\nFinding Muse device...")
    device = await client.find_device(name_filter="Muse")
    
    if not device:
        print("No device found")
        return
    
    print(f"Found: {device.name} ({device.address})")
    
    # Stream for 10 seconds
    print("\nStarting 10-second stream...")
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=10
    )
    
    if success:
        print("\nStreaming complete!")
        summary = client.get_summary()
        print(f"Received {summary['packets_received']} packets")


async def example_custom_visualization():
    """Example: Custom buffer sizes for visualization"""
    print("\n" + "=" * 60)
    print("Custom Visualization Buffers")
    print("=" * 60)
    
    from muse_visualizer import MuseVisualizer
    
    # Create visualizer with custom buffer size
    # 5 seconds of data = 1280 samples at 256 Hz
    print("\nCreating visualizer with 5-second buffer...")
    viz = MuseVisualizer(
        backend='auto',
        window_size=1280  # 5 seconds at 256 Hz
    )
    
    print("Visualizer created with:")
    print("  EEG buffer: 1280 samples (5 seconds)")
    print("  PPG buffer: 320 samples (5 seconds)")
    print("  IMU buffer: 260 samples (5 seconds)")
    
    # You can also specify different update rates
    viz2 = MuseVisualizer(
        backend='auto',
        window_size=2560,  # 10 seconds
        update_rate=60     # 60 Hz refresh
    )
    
    print("\nOr with different parameters:")
    print("  window_size=2560 (10 seconds)")
    print("  update_rate=60 (60 Hz refresh)")


async def example_complete_workflow():
    """Example: Complete workflow from discovery to streaming"""
    print("\n" + "=" * 60)
    print("Complete Workflow")
    print("=" * 60)
    
    # Step 1: Find devices
    print("\nStep 1: Finding devices...")
    devices = await find_muse_devices()
    
    if not devices:
        print("No devices found")
        return
    
    # Step 2: Select device
    print("\nStep 2: Selecting device...")
    device = await select_device(devices)
    
    if not device:
        print("No device selected")
        return
    
    # Step 3: Create client and stream
    print(f"\nStep 3: Streaming from {device.name}...")
    
    client = MuseStreamClient()
    
    # Use the address directly
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=5
    )
    
    if success:
        print("\nSuccess! Streaming complete")
        
        # If you want to save the address for next time,
        # that's up to you - maybe in a simple text file:
        # with open("my_muse.txt", "w") as f:
        #     f.write(device.address)


async def main():
    """Main example runner"""
    print("Amused - Simple Device Discovery Examples")
    print("=" * 60)
    print("\nThese examples show the clean, minimal approach")
    print("No config files, no persistence - just simple discovery\n")
    
    examples = [
        ("Basic Discovery", example_basic_discovery),
        ("Device Selection", example_device_selection),
        ("Direct Connection", example_direct_connection),
        ("Simple Streaming", example_streaming_simple),
        ("Custom Visualization", example_custom_visualization),
        ("Complete Workflow", example_complete_workflow),
    ]
    
    print("Available examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"{i}. {name}")
    
    try:
        choice = input("\nSelect example (1-6): ")
        idx = int(choice) - 1
        
        if 0 <= idx < len(examples):
            name, func = examples[idx]
            print(f"\nRunning: {name}")
            await func()
        else:
            print("Invalid choice")
            
    except KeyboardInterrupt:
        print("\n\nCancelled")
    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    # Windows event loop fix
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())