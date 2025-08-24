"""
Record real test data from Muse S for unit tests
This creates a binary file with real packets that can be used in tests
"""

import asyncio
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_stream_client import MuseStreamClient

async def record_test_packets():
    """Record a short session of real packets for testing"""
    
    print("=" * 60)
    print("Recording Real Test Data from Muse S")
    print("=" * 60)
    
    # Create client that saves raw packets
    client = MuseStreamClient(
        save_raw=True,
        decode_realtime=False,  # Don't decode, just save raw
        data_dir="test_data",
        verbose=True
    )
    
    # Find device
    print("\nSearching for Muse device...")
    device = await client.find_device()
    
    if not device:
        print("No Muse device found!")
        print("\nMake sure your Muse S is:")
        print("1. Powered on")
        print("2. In pairing mode")
        print("3. Not connected to another device")
        return None
    
    print(f"Found: {device.name}")
    
    # Record for just 5 seconds to get sample packets
    duration = 5
    print(f"\nRecording {duration} seconds of data for tests...")
    
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=duration,
        preset='p1034'  # Full sensor suite
    )
    
    if success:
        summary = client.get_summary()
        if 'file_info' in summary:
            binary_file = summary['file_info']['filepath']
            print(f"\n[OK] Recorded to: {binary_file}")
            
            # Also save some metadata about the packets
            metadata = {
                'duration': duration,
                'packets_received': summary['packets_received'],
                'file': binary_file,
                'description': 'Real Muse S test data for unit tests'
            }
            
            metadata_file = binary_file.replace('.bin', '_metadata.json')
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"[OK] Metadata saved to: {metadata_file}")
            
            # Extract a few sample packets for inline test use
            print("\nExtracting sample packets for tests...")
            extract_sample_packets(binary_file)
            
            return binary_file
    
    return None

def extract_sample_packets(binary_file):
    """Extract some real packets for use in tests"""
    from muse_raw_stream import MuseRawStream
    
    stream = MuseRawStream(binary_file)
    stream.open_read()
    
    sample_packets = {
        'eeg_packets': [],
        'imu_packets': [],
        'mixed_packets': []
    }
    
    count = 0
    for packet in stream.read_packets():
        if count >= 100:  # Get first 100 packets
            break
            
        # Categorize by type
        if packet.packet_type == 0xDF:
            if len(sample_packets['eeg_packets']) < 5:
                sample_packets['eeg_packets'].append({
                    'hex': packet.data.hex(),
                    'type': packet.packet_type,
                    'size': len(packet.data)
                })
        elif packet.packet_type == 0xF4:
            if len(sample_packets['imu_packets']) < 5:
                sample_packets['imu_packets'].append({
                    'hex': packet.data.hex(),
                    'type': packet.packet_type,
                    'size': len(packet.data)
                })
        else:
            if len(sample_packets['mixed_packets']) < 5:
                sample_packets['mixed_packets'].append({
                    'hex': packet.data.hex(),
                    'type': packet.packet_type,
                    'size': len(packet.data)
                })
        
        count += 1
    
    stream.close()
    
    # Save sample packets
    samples_file = binary_file.replace('.bin', '_samples.json')
    with open(samples_file, 'w') as f:
        json.dump(sample_packets, f, indent=2)
    
    print(f"[OK] Sample packets saved to: {samples_file}")
    
    # Create Python test data file
    create_test_data_module(sample_packets)

def create_test_data_module(sample_packets):
    """Create a Python module with real test data"""
    
    test_data_content = '''"""
Real test data captured from Muse S
Auto-generated - do not edit manually
"""

# Real EEG/PPG packets (type 0xDF)
REAL_EEG_PACKETS = [
'''
    
    for packet in sample_packets['eeg_packets'][:3]:
        test_data_content += f'    bytes.fromhex("{packet["hex"]}"),\n'
    
    test_data_content += ''']

# Real IMU packets (type 0xF4)
REAL_IMU_PACKETS = [
'''
    
    for packet in sample_packets['imu_packets'][:3]:
        test_data_content += f'    bytes.fromhex("{packet["hex"]}"),\n'
    
    test_data_content += ''']

# Real mixed packets
REAL_MIXED_PACKETS = [
'''
    
    for packet in sample_packets['mixed_packets'][:3]:
        test_data_content += f'    bytes.fromhex("{packet["hex"]}"),\n'
    
    test_data_content += ''']

def get_test_packet(packet_type='eeg'):
    """Get a real test packet by type"""
    if packet_type == 'eeg' and REAL_EEG_PACKETS:
        return REAL_EEG_PACKETS[0]
    elif packet_type == 'imu' and REAL_IMU_PACKETS:
        return REAL_IMU_PACKETS[0]
    elif packet_type == 'mixed' and REAL_MIXED_PACKETS:
        return REAL_MIXED_PACKETS[0]
    else:
        # Return a synthetic packet if no real data
        return bytes([0xDF, 0x00, 0x00, 0x00] + [0x80] * 100)
'''
    
    # Get the correct path - we're already in tests directory
    test_data_path = 'real_test_data.py'
    with open(test_data_path, 'w') as f:
        f.write(test_data_content)
    
    print(f"[OK] Test data module created: {test_data_path}")

async def main():
    """Main function"""
    print("\nThis will record real data from your Muse S for testing.")
    print("The data will be used to ensure tests use realistic packets.\n")
    
    binary_file = await record_test_packets()
    
    if binary_file:
        print("\n" + "=" * 60)
        print("SUCCESS! Test data recorded.")
        print("=" * 60)
        print("\nYou can now run tests with real data:")
        print("  python -m pytest tests/")
        print("\nThe tests will use the real packets in tests/real_test_data.py")
    else:
        print("\nRecording failed. Creating synthetic test data instead...")
        # Create synthetic data as fallback
        create_test_data_module({
            'eeg_packets': [],
            'imu_packets': [],
            'mixed_packets': []
        })

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        # Create fallback synthetic data
        create_test_data_module({
            'eeg_packets': [],
            'imu_packets': [],
            'mixed_packets': []
        })