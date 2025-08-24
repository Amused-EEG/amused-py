"""
Example 2: Full Sensor Suite
This example demonstrates accessing ALL sensors including EEG, PPG, fNIRS, and IMU.
This is what you want for real applications!
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_sleep_client import MuseSleepClient

async def main():
    """Monitor all sensors for a short duration"""
    
    print("=" * 60)
    print("Amused Example: Full Sensor Suite")
    print("=" * 60)
    print("\nThis enables ALL sensors like the Muse app's sleep mode:")
    print("- EEG (brain waves)")
    print("- PPG (heart rate)")
    print("- fNIRS (blood oxygenation)")
    print("- IMU (motion)")
    
    # Create client with custom log directory
    client = MuseSleepClient(log_dir="example_data", verbose=True)
    
    # Find device
    print("\nSearching for Muse S device...")
    device = await client.find_device()
    
    if not device:
        print("No Muse device found!")
        return
    
    print(f"Found: {device.name}")
    
    # Monitor for 2 minutes (0.033 hours)
    duration_hours = 0.033  # 2 minutes
    
    print(f"\nStarting full sensor monitoring for {duration_hours*60:.0f} minutes...")
    print("Data will be saved to example_data/ directory")
    
    success = await client.connect_and_monitor(device.address, duration_hours)
    
    # Get session summary
    summary = client.get_summary()
    
    print("\n" + "=" * 60)
    print("SESSION SUMMARY")
    print("=" * 60)
    print(f"Duration: {summary['duration_seconds']:.0f} seconds")
    print(f"Packets received: {summary['packets_received']}")
    print(f"Battery level: {summary['battery_percent']}%")
    
    # Show heart rate if available
    if summary.get('heart_rate_stats'):
        hr = summary['heart_rate_stats']
        print(f"\nHeart Rate Statistics:")
        print(f"  Average: {hr.get('avg_heart_rate', 0):.0f} BPM")
        print(f"  Min: {hr.get('min_heart_rate', 0):.0f} BPM")
        print(f"  Max: {hr.get('max_heart_rate', 0):.0f} BPM")
    
    print("\n" + "=" * 60)
    
    if success:
        print("Success! Check example_data/ for the CSV file")
    else:
        print("Session had issues. Check the logs above.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMonitoring interrupted by user")
    except Exception as e:
        print(f"Error: {e}")