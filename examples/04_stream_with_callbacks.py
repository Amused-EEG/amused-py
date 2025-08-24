"""
Example 4: Real-time Streaming with Callbacks
Shows how to process data in real-time without saving
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_stream_client import MuseStreamClient
import numpy as np

# Global storage for analysis
eeg_buffer = []
heart_rates = []
imu_motion = []

def process_eeg(data):
    """Process EEG data in real-time"""
    global eeg_buffer
    
    # data contains {'channels': {'TP9': [...], 'AF7': [...], ...}, 'timestamp': ...}
    if 'channels' in data and data['channels']:
        # Get first channel
        first_channel = list(data['channels'].keys())[0]
        samples = data['channels'][first_channel]
        
        # Add to buffer
        eeg_buffer.extend(samples)
        
        # Keep only last 5 seconds (256 Hz * 5)
        eeg_buffer = eeg_buffer[-1280:]
        
        # Calculate simple metrics
        if len(eeg_buffer) >= 256:
            recent = np.array(eeg_buffer[-256:])  # Last second
            mean_amplitude = np.mean(np.abs(recent))
            
            # Simple alpha detection (8-12 Hz)
            # This is simplified - real analysis would use FFT
            crossings = np.where(np.diff(np.sign(recent)))[0]
            freq_estimate = len(crossings) / 2.0  # Rough frequency
            
            print(f"EEG: Mean amplitude: {mean_amplitude:.1f} μV, ~{freq_estimate:.0f} Hz")

def process_heart_rate(hr):
    """Process heart rate data"""
    global heart_rates
    
    heart_rates.append(hr)
    
    # Calculate HRV if we have enough data
    if len(heart_rates) >= 5:
        recent_hrs = heart_rates[-5:]
        hrv = np.std(recent_hrs)
        avg_hr = np.mean(recent_hrs)
        
        print(f"Heart Rate: {hr:.0f} BPM (Avg: {avg_hr:.0f}, HRV: {hrv:.1f})")
    else:
        print(f"Heart Rate: {hr:.0f} BPM")

def process_imu(data):
    """Process IMU motion data"""
    global imu_motion
    
    if 'accel' in data and data['accel']:
        accel = data['accel']
        # Calculate magnitude
        magnitude = np.sqrt(sum(x**2 for x in accel))
        imu_motion.append(magnitude)
        
        # Detect movement
        if len(imu_motion) >= 10:
            recent_motion = imu_motion[-10:]
            motion_variance = np.var(recent_motion)
            
            if motion_variance > 0.1:
                print(f"IMU: Movement detected! (variance: {motion_variance:.2f})")
            else:
                print(f"IMU: Still (accel magnitude: {magnitude:.2f})")

def process_raw_packet(packet_bytes):
    """Process raw packet data"""
    # You could do custom packet analysis here
    packet_type = packet_bytes[0] if packet_bytes else 0
    
    # Log packet types periodically
    if packet_type == 0xDF:
        pass  # EEG/PPG packet
    elif packet_type == 0xF4:
        pass  # IMU packet
    # Add more as needed

async def main():
    """Main streaming example with callbacks"""
    
    print("=" * 60)
    print("Amused Example: Real-time Processing with Callbacks")
    print("=" * 60)
    print("\nThis example shows how to:")
    print("- Stream without saving data")
    print("- Process EEG in real-time")
    print("- Track heart rate changes")
    print("- Detect motion from IMU")
    
    # Create client without saving (save_raw=False is default)
    client = MuseStreamClient(
        save_raw=False,  # Don't save to disk
        decode_realtime=True,  # Do decode for callbacks
        verbose=True
    )
    
    # Register callbacks for different data types
    print("\nRegistering callbacks...")
    client.on_eeg(process_eeg)
    client.on_heart_rate(process_heart_rate)
    client.on_imu(process_imu)
    # client.on_packet(process_raw_packet)  # Uncomment for raw packets
    
    # Find device
    print("\nSearching for Muse device...")
    device = await client.find_device()
    
    if not device:
        print("No Muse device found!")
        return
    
    print(f"Found: {device.name}")
    
    # Stream for 30 seconds
    duration = 30
    print(f"\nStreaming for {duration} seconds...")
    print("Watch for real-time updates below:\n")
    
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=duration,
        preset='p1034'  # Full sensor suite
    )
    
    if success:
        # Show final summary
        print("\n" + "=" * 60)
        print("STREAMING COMPLETE - Summary")
        print("=" * 60)
        
        summary = client.get_summary()
        print(f"Total packets: {summary['packets_received']}")
        
        if 'eeg_samples' in summary:
            print(f"EEG samples: {summary['eeg_samples']}")
        
        if heart_rates:
            print(f"\nHeart Rate Statistics:")
            print(f"  Min: {min(heart_rates):.0f} BPM")
            print(f"  Max: {max(heart_rates):.0f} BPM")
            print(f"  Average: {np.mean(heart_rates):.0f} BPM")
            print(f"  Std Dev: {np.std(heart_rates):.1f} BPM")
        
        if imu_motion:
            print(f"\nMotion Statistics:")
            print(f"  Total samples: {len(imu_motion)}")
            print(f"  Average magnitude: {np.mean(imu_motion):.2f}")
            print(f"  Max magnitude: {max(imu_motion):.2f}")
        
        print("\nNo data was saved to disk (streaming only)")
    else:
        print("\nStreaming failed. Check device connection.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStreaming interrupted by user")
        
        # Show what we collected
        if heart_rates:
            print(f"Collected {len(heart_rates)} heart rate measurements")
        if eeg_buffer:
            print(f"Collected {len(eeg_buffer)} EEG samples")
        if imu_motion:
            print(f"Collected {len(imu_motion)} motion samples")