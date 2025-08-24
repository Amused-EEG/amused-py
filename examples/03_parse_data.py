"""
Example 3: Parse Recorded Data
This example shows how to parse and extract sensor data from a recorded binary session.
"""

import sys
import os
import glob
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_raw_stream import MuseRawStream
from muse_realtime_decoder import MuseRealtimeDecoder

def main():
    """Parse the most recent recording"""
    
    print("=" * 60)
    print("Amused Example: Parse Recorded Data")
    print("=" * 60)
    
    # Find binary files
    bin_files = glob.glob("muse_data/*.bin")
    
    if not bin_files:
        print("\nNo recorded sessions found!")
        print("Run example 02_full_sensors.py first to record data.")
        return
    
    # Get most recent file
    latest_file = max(bin_files, key=os.path.getctime)
    print(f"\nParsing: {latest_file}")
    
    # Open binary stream for reading
    stream = MuseRawStream(latest_file)
    stream.open_read()
    
    # Get file info
    info = stream.get_file_info()
    print(f"\nFile Info:")
    print(f"  Packets: {info['packet_count']}")
    print(f"  Duration: {info['duration_seconds']:.1f} seconds")
    print(f"  Size: {info['file_size_mb']:.2f} MB")
    
    # Create decoder
    decoder = MuseRealtimeDecoder()
    
    # Statistics
    stats = {
        'eeg_count': 0,
        'ppg_count': 0,
        'imu_count': 0,
        'heart_rates': []
    }
    
    print("\nExtracting sensor data...")
    
    # Read and decode packets
    packet_num = 0
    sample_eeg_shown = False
    
    for packet in stream.read_packets():
        packet_num += 1
        
        # Decode packet
        decoded = decoder.decode(packet.data, packet.timestamp)
        
        # Count data types
        if decoded.eeg:
            stats['eeg_count'] += 1
            
            # Show sample EEG data (first packet only)
            if not sample_eeg_shown:
                print(f"\nSample EEG values (uV) from packet {packet_num}:")
                for channel, values in list(decoded.eeg.items())[:3]:
                    if values and len(values) > 2:
                        print(f"  {channel}: {values[0]:.1f}, {values[1]:.1f}, {values[2]:.1f}...")
                sample_eeg_shown = True
        
        if decoded.ppg:
            stats['ppg_count'] += 1
        
        if decoded.imu:
            stats['imu_count'] += 1
        
        if decoded.heart_rate:
            stats['heart_rates'].append(decoded.heart_rate)
    
    # Close stream
    stream.close()
    
    # Get decoder stats
    decoder_stats = decoder.get_stats()
    
    print("\n" + "=" * 60)
    print("EXTRACTED DATA SUMMARY")
    print("=" * 60)
    
    print(f"\nPackets Processed:")
    print(f"  Total: {packet_num}")
    print(f"  With EEG: {stats['eeg_count']}")
    print(f"  With PPG: {stats['ppg_count']}")
    print(f"  With IMU: {stats['imu_count']}")
    
    print(f"\nSamples Decoded:")
    print(f"  EEG: {decoder_stats['eeg_samples']}")
    print(f"  PPG: {decoder_stats['ppg_samples']}")
    print(f"  IMU: {decoder_stats['imu_samples']}")
    
    if stats['heart_rates']:
        avg_hr = sum(stats['heart_rates']) / len(stats['heart_rates'])
        print(f"\nHeart Rate:")
        print(f"  Average: {avg_hr:.1f} BPM")
        print(f"  Min: {min(stats['heart_rates']):.1f} BPM")
        print(f"  Max: {max(stats['heart_rates']):.1f} BPM")
    
    if decoder_stats['decode_errors'] > 0:
        print(f"\nDecode errors: {decoder_stats['decode_errors']}")
    
    print("\n" + "=" * 60)
    print("Data successfully extracted and ready for analysis!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()