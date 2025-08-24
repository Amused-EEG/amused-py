"""
Example 5: Save Binary Data and Replay
Shows how to save streaming data in binary format and replay it later
"""

import asyncio
import sys
import os
import glob
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_stream_client import MuseStreamClient, stream_and_save
from muse_replay import MuseReplayPlayer, MuseBinaryParser

async def record_session():
    """Record a session to binary format"""
    
    print("=" * 60)
    print("Part 1: Recording Session to Binary")
    print("=" * 60)
    
    # Create client that saves to binary
    client = MuseStreamClient(
        save_raw=True,  # Enable binary saving
        decode_realtime=True,
        data_dir="recorded_sessions",
        verbose=True
    )
    
    # Find device
    device = await client.find_device()
    if not device:
        print("No Muse device found!")
        return None
    
    print(f"Found: {device.name}")
    
    # Record for 20 seconds
    duration = 20
    print(f"\nRecording for {duration} seconds...")
    
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=duration,
        preset='p1034'
    )
    
    if success:
        summary = client.get_summary()
        if 'file_info' in summary:
            filepath = summary['file_info']['filepath']
            print(f"\n✓ Recorded to: {filepath}")
            print(f"  File size: {summary['file_info']['file_size_mb']:.2f} MB")
            print(f"  Packets: {summary['file_info']['packet_count']}")
            return filepath
    
    return None

async def replay_session(filepath):
    """Replay a recorded session"""
    
    print("\n" + "=" * 60)
    print("Part 2: Replaying Recorded Session")
    print("=" * 60)
    
    if not filepath or not os.path.exists(filepath):
        # Find most recent recording
        recordings = glob.glob("recorded_sessions/*.bin") + glob.glob("muse_data/*.bin")
        if not recordings:
            print("No recordings found!")
            return
        filepath = max(recordings, key=os.path.getctime)
    
    print(f"Replaying: {filepath}")
    
    # Create replay player
    player = MuseReplayPlayer(
        filepath=filepath,
        speed=2.0,  # Play at 2x speed
        decode=True,
        verbose=True
    )
    
    # Get info about recording
    info = player.get_info()
    print(f"Recording duration: {info['duration_seconds']:.1f} seconds")
    print(f"Total packets: {info['total_packets']}")
    
    # Register callbacks to process replayed data
    packet_count = 0
    eeg_count = 0
    hr_values = []
    
    def on_decoded(data):
        nonlocal packet_count, eeg_count, hr_values
        packet_count += 1
        
        if data.eeg:
            eeg_count += 1
            if eeg_count % 100 == 0:
                print(f"  Replayed {eeg_count} EEG packets")
        
        if data.heart_rate:
            hr_values.append(data.heart_rate)
            print(f"  Heart Rate: {data.heart_rate:.0f} BPM")
    
    def on_progress(progress):
        if int(progress * 100) % 20 == 0:
            print(f"Replay progress: {progress:.0%}")
    
    def on_complete():
        print("\nReplay complete!")
    
    player.on_decoded(on_decoded)
    player.on_progress(on_progress)
    player.on_complete(on_complete)
    
    # Play first 10 seconds at 2x speed
    print(f"\nReplaying first 10 seconds at 2x speed...")
    await player.play(
        start_time=0,
        duration=10,
        realtime=True  # Maintain timing relationships
    )
    
    print(f"\nReplay Statistics:")
    print(f"  Packets processed: {packet_count}")
    print(f"  EEG packets: {eeg_count}")
    if hr_values:
        import numpy as np
        print(f"  Heart rates detected: {len(hr_values)}")
        print(f"  Average HR: {np.mean(hr_values):.0f} BPM")

def analyze_recording(filepath):
    """Analyze a recording without replay"""
    
    print("\n" + "=" * 60)
    print("Part 3: Batch Analysis of Recording")
    print("=" * 60)
    
    if not filepath or not os.path.exists(filepath):
        recordings = glob.glob("recorded_sessions/*.bin") + glob.glob("muse_data/*.bin")
        if not recordings:
            print("No recordings found!")
            return
        filepath = max(recordings, key=os.path.getctime)
    
    print(f"Analyzing: {filepath}")
    
    # Parse the entire file
    parser = MuseBinaryParser(filepath)
    results = parser.parse_all()
    
    print(f"\nAnalysis Results:")
    print(f"  Duration: {results['duration']:.1f} seconds")
    print(f"  Total packets: {results['total_packets']}")
    
    print(f"\nPacket Types:")
    for ptype, count in results['packet_types'].items():
        print(f"  {ptype}: {count}")
    
    print(f"\nSensor Data:")
    print(f"  EEG segments: {len(results['eeg_data'])}")
    print(f"  PPG segments: {len(results['ppg_data'])}")
    print(f"  IMU segments: {len(results['imu_data'])}")
    
    if results['heart_rates']:
        import numpy as np
        hrs = [hr['bpm'] for hr in results['heart_rates']]
        print(f"\nHeart Rate Analysis:")
        print(f"  Measurements: {len(hrs)}")
        print(f"  Average: {np.mean(hrs):.0f} BPM")
        print(f"  Min: {min(hrs):.0f} BPM")
        print(f"  Max: {max(hrs):.0f} BPM")
    
    # Extract a specific time range
    print(f"\nExtracting packets from 5-10 seconds...")
    packets = parser.extract_time_range(5.0, 10.0)
    print(f"  Found {len(packets)} packets in that range")
    
    # Show file efficiency
    from muse_raw_stream import MuseRawStream
    stream = MuseRawStream(filepath)
    info = stream.get_file_info()
    print(f"\nFile Efficiency:")
    print(f"  File size: {info['file_size_mb']:.2f} MB")
    print(f"  Average packet size: {info['average_packet_size']:.0f} bytes")
    print(f"  Packets per second: {info['packets_per_second']:.1f}")
    print(f"  Compression: ~10x smaller than CSV")

async def main():
    """Main example flow"""
    
    print("Amused Example: Binary Recording and Replay")
    print("=" * 60)
    print("\nThis example demonstrates:")
    print("1. Recording to efficient binary format")
    print("2. Replaying recordings at different speeds")
    print("3. Batch analysis of recorded data")
    
    # Check if we should record or use existing
    recordings = glob.glob("recorded_sessions/*.bin") + glob.glob("muse_data/*.bin")
    
    if recordings:
        print(f"\nFound {len(recordings)} existing recordings")
        choice = input("Record new session (r) or use existing (e)? [e]: ").lower()
        
        if choice == 'r':
            filepath = await record_session()
        else:
            filepath = max(recordings, key=os.path.getctime)
            print(f"Using: {filepath}")
    else:
        print("\nNo existing recordings found. Starting new recording...")
        filepath = await record_session()
    
    if filepath:
        # Replay the recording
        await replay_session(filepath)
        
        # Analyze the recording
        analyze_recording(filepath)
        
        print("\n" + "=" * 60)
        print("Example complete!")
        print(f"Binary file saved at: {filepath}")
        print("You can replay this file anytime without the Muse device")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()