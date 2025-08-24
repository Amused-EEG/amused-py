"""
Example 1: Basic EEG Streaming
This example shows how to connect to a Muse S and stream basic EEG data.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices

async def main():
    """Stream EEG data for 30 seconds"""
    
    print("=" * 60)
    print("Amused Example: Basic EEG Streaming")
    print("=" * 60)
    
    # Create client (no saving, just streaming)
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=True
    )
    
    # Find Muse device
    print("\nSearching for Muse S device...")
    devices = await find_muse_devices(timeout=5.0)
    
    if not devices:
        print("No Muse device found! Please ensure:")
        print("- Your Muse S is turned on")
        print("- Bluetooth is enabled")
        print("- Device is in pairing mode")
        return
    
    device = devices[0]
    print(f"Found device: {device.name} ({device.address})")
    
    # Connect and stream
    print("\nConnecting and streaming EEG data...")
    print("This will stream for 30 seconds...")
    
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=30,
        preset='p1035'  # Full sensor mode
    )
    
    if success:
        summary = client.get_summary()
        print("\n" + "=" * 60)
        print("Streaming completed successfully!")
        print(f"Total packets received: {summary['packets_received']}")
        if 'eeg_samples' in summary:
            print(f"EEG samples collected: {summary['eeg_samples']}")
        if 'ppg_samples' in summary:
            print(f"PPG samples collected: {summary['ppg_samples']}")
        print("=" * 60)
    else:
        print("\nStreaming failed. Please check device connection.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStreaming interrupted by user")
    except Exception as e:
        print(f"Error: {e}")