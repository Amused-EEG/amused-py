"""
Example 1: Basic EEG Streaming
This example shows how to connect to a Muse S and stream basic EEG data.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_exact_client import MuseClient

async def main():
    """Stream EEG data for 30 seconds"""
    
    print("=" * 60)
    print("Amused Example: Basic EEG Streaming")
    print("=" * 60)
    
    # Create client
    client = MuseClient(verbose=True)
    
    # Find Muse device
    print("\nSearching for Muse S device...")
    device = await client.find_device()
    
    if not device:
        print("No Muse device found! Please ensure:")
        print("- Your Muse S is turned on")
        print("- Bluetooth is enabled")
        print("- Device is in pairing mode")
        return
    
    print(f"Found device: {device.name} ({device.address})")
    
    # Connect and stream
    print("\nConnecting and streaming EEG data...")
    print("This will stream for 30 seconds...")
    
    success = await client.connect_and_stream(device.address)
    
    if success:
        print("\n" + "=" * 60)
        print("Streaming completed successfully!")
        print(f"Total packets received: {client.packet_count}")
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