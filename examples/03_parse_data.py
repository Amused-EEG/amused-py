"""
Example 3: Parse Recorded Data
This example shows how to parse and extract sensor data from a recorded session.
"""

import sys
import os
import glob
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_integrated_parser import MuseIntegratedParser

def main():
    """Parse the most recent recording"""
    
    print("=" * 60)
    print("Amused Example: Parse Recorded Data")
    print("=" * 60)
    
    # Find CSV files
    csv_files = glob.glob("example_data/*.csv") + glob.glob("sleep_data/*.csv")
    
    if not csv_files:
        print("\nNo recorded sessions found!")
        print("Run example 02_full_sensors.py first to record data.")
        return
    
    # Get most recent file
    latest_file = max(csv_files, key=os.path.getctime)
    print(f"\nParsing: {latest_file}")
    
    # Create parser
    parser = MuseIntegratedParser()
    
    # Parse the file
    print("\nExtracting sensor data...")
    data = parser.parse_csv_file(latest_file)
    
    # Get summary
    summary = parser.get_summary()
    
    print("\n" + "=" * 60)
    print("EXTRACTED DATA SUMMARY")
    print("=" * 60)
    
    print(f"\nPackets Processed:")
    print(f"  Total: {summary['total_packets']}")
    print(f"  EEG: {summary['eeg_packets']}")
    print(f"  IMU: {summary['imu_packets']}")
    print(f"  PPG: {summary['ppg_packets']}")
    
    if summary.get('eeg_channels'):
        print(f"\nEEG Channels Found: {len(summary['eeg_channels'])}")
        print(f"  {', '.join(summary['eeg_channels'][:5])}...")
    
    if summary['has_heart_rate']:
        print(f"\nHeart Rate: Data available for analysis")
    
    if summary['has_fnirs']:
        print(f"fNIRS: Blood oxygenation data available")
    
    # Show sample data
    if data and len(data) > 0:
        print(f"\n{len(data)} data packets extracted")
        
        # Show first packet with EEG data
        for packet in data[:10]:
            if packet.eeg_channels:
                print(f"\nSample EEG values (μV) from packet {packet.packet_num}:")
                for channel, values in list(packet.eeg_channels.items())[:2]:
                    if values:
                        print(f"  {channel}: {values[0]:.1f}, {values[1]:.1f}, {values[2]:.1f}...")
                break
    
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