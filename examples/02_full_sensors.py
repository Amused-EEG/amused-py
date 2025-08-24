"""
Example 2: Full Sensor Suite
This example demonstrates recording ALL sensors including EEG, PPG, and IMU to a binary file.
Data is saved in efficient binary format for later analysis.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices

async def main():
    """Record all sensors for a short duration"""
    
    print("=" * 60)
    print("Amused Example: Full Sensor Recording")
    print("=" * 60)
    print("\nThis records ALL sensors:")
    print("- EEG (7 channels)")
    print("- PPG (heart rate)")
    print("- IMU (motion)")
    
    # Find device first
    print("\nSearching for Muse S device...")
    devices = await find_muse_devices(timeout=5.0)
    
    if not devices:
        print("No Muse device found!")
        return
    
    device = devices[0]
    print(f"Found: {device.name}")
    
    # Create client with binary saving enabled
    client = MuseStreamClient(
        save_raw=True,  # Enable binary saving
        decode_realtime=True,  # Also decode in real-time for stats
        data_dir="muse_data",  # Save to muse_data directory
        verbose=True
    )
    
    # Record for 30 seconds
    duration_seconds = 30
    
    print(f"\nStarting full sensor recording for {duration_seconds} seconds...")
    print("Data will be saved to muse_data/ directory")
    
    # Register callback to show heart rate
    def on_heart_rate(hr):
        if hr:
            print(f"  Heart Rate: {hr:.0f} BPM")
    
    client.on_heart_rate(on_heart_rate)
    
    # Connect and stream
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=duration_seconds,
        preset='p1035'  # Full sensor mode
    )
    
    # Get session summary
    summary = client.get_summary()
    
    print("\n" + "=" * 60)
    print("SESSION SUMMARY")
    print("=" * 60)
    print(f"Duration: {duration_seconds} seconds")
    print(f"Packets received: {summary['packets_received']}")
    
    if 'eeg_samples' in summary:
        print(f"EEG samples: {summary['eeg_samples']}")
    if 'ppg_samples' in summary:
        print(f"PPG samples: {summary['ppg_samples']}")
    if 'imu_samples' in summary:
        print(f"IMU samples: {summary['imu_samples']}")
    
    if summary.get('last_heart_rate'):
        print(f"\nLast Heart Rate: {summary['last_heart_rate']:.0f} BPM")
    
    if 'file_info' in summary:
        info = summary['file_info']
        print(f"\nData saved to: {info['filepath']}")
        print(f"File size: {info['file_size_mb']:.2f} MB")
    
    print("\n" + "=" * 60)
    
    if success:
        print("Success! Run example 03_parse_data.py to analyze the recording")
    else:
        print("Recording had issues. Check the logs above.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMonitoring interrupted by user")
    except Exception as e:
        print(f"Error: {e}")