"""
Example 6: Real-time Visualization (Windows Fix)
Complete fix for Windows Qt/Bleak conflict

This version properly isolates BLE operations from Qt
"""

import asyncio
import sys
import os
import threading
import time
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_visualizer import MuseVisualizer, PYQTGRAPH_AVAILABLE, PLOTLY_AVAILABLE
from muse_discovery_gui import scan_in_thread
from muse_realtime_decoder import MuseRealtimeDecoder
from bleak import BleakClient
import numpy as np

# Global visualizer and decoder
viz = None
decoder = None
packet_count = 0

# BLE UUIDs
CONTROL_CHAR_UUID = "273e0001-4c4d-454d-96be-f03bac821358"
SENSOR_CHAR_UUID = "273e0013-4c4d-454d-96be-f03bac821358"

# Commands
COMMANDS = {
    'halt': bytes.fromhex('02680a'),
    'p1034': bytes.fromhex('0670313033340a'),
    'dc001': bytes.fromhex('0664633030310a'),
    'L1': bytes.fromhex('034c310a'),
}

def process_packet(sender, data):
    """Process incoming BLE packet"""
    global viz, decoder, packet_count
    
    if not viz or not decoder:
        return
    
    packet_count += 1
    
    # Decode the packet
    decoded = decoder.decode(bytes(data), datetime.now())
    
    # Update visualization based on decoded data
    if decoded.eeg and viz:
        eeg_data = {
            'channels': decoded.eeg,
            'timestamp': datetime.now().timestamp()
        }
        viz.update_eeg(eeg_data)
        
        # Print first channel value for feedback
        first_channel = next(iter(decoded.eeg.keys()))
        if decoded.eeg[first_channel]:
            print(f"Packets: {packet_count} | {first_channel}: {decoded.eeg[first_channel][0]:.1f} μV", end='\r')
    
    if decoded.ppg and viz:
        ppg_data = {
            'samples': decoded.ppg.get('samples', []),
            'timestamp': datetime.now().timestamp()
        }
        viz.update_ppg(ppg_data)
    
    if decoded.heart_rate and viz:
        viz.update_heart_rate(decoded.heart_rate)
    
    if decoded.imu and viz:
        imu_data = {
            'accel': decoded.imu.get('accel', []),
            'gyro': decoded.imu.get('gyro', []),
            'timestamp': datetime.now().timestamp()
        }
        viz.update_imu(imu_data)


def stream_in_thread(address: str, duration: int, viz_obj):
    """
    Stream data in a separate thread with its own event loop
    
    This completely isolates BLE operations from Qt
    """
    global viz, decoder
    viz = viz_obj
    decoder = MuseRealtimeDecoder()
    
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def stream():
        print(f"\n[Thread] Connecting to {address}...")
        
        try:
            async with BleakClient(address) as client:
                if not client.is_connected:
                    print("[Thread] Failed to connect")
                    return
                
                print("[Thread] Connected!")
                
                # Send initialization commands
                print("[Thread] Initializing device...")
                
                # Enable control notifications first
                control_notify = "273e0001-4c4d-454d-96be-f03bac821358"
                try:
                    await client.start_notify(control_notify, lambda s, d: print(f"[Control] {d.hex()}"))
                    print("[Thread] Enabled control notifications")
                except Exception as e:
                    print(f"[Thread] Control notify error: {e}")
                
                # Send initialization commands
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['halt'])
                await asyncio.sleep(0.5)
                
                # Set preset for full sensors
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['p1034'])
                await asyncio.sleep(0.5)
                
                # Start streaming (send TWICE as required)
                print("[Thread] Sending dc001 command (twice)...")
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'])
                await asyncio.sleep(0.2)
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'])
                await asyncio.sleep(0.2)
                
                # Send L1 to maintain stream
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['L1'])
                await asyncio.sleep(0.2)
                
                # Subscribe to notifications on all sensor characteristics
                print("[Thread] Starting notifications...")
                
                # List all available characteristics
                services = client.services
                print("[Thread] Available characteristics:")
                for service in services:
                    for char in service.characteristics:
                        if "273e" in str(char.uuid):
                            print(f"  - {char.uuid} (notify: {'notify' in char.properties})")
                
                # Try to enable notifications on the main sensor characteristic
                # This is typically 0x0013 for combined data
                main_sensor = "273e0013-4c4d-454d-96be-f03bac821358"
                try:
                    await client.start_notify(main_sensor, process_packet)
                    print(f"[Thread] ✓ Enabled notifications on main sensor")
                except Exception as e:
                    print(f"[Thread] ✗ Main sensor error: {e}")
                    
                    # Try individual EEG channels as fallback
                    eeg_chars = [
                        "273e0003-4c4d-454d-96be-f03bac821358",  # TP9
                        "273e0004-4c4d-454d-96be-f03bac821358",  # AF7
                        "273e0005-4c4d-454d-96be-f03bac821358",  # AF8
                        "273e0006-4c4d-454d-96be-f03bac821358",  # TP10
                    ]
                    
                    for char_uuid in eeg_chars:
                        try:
                            await client.start_notify(char_uuid, process_packet)
                            print(f"[Thread] ✓ Enabled {char_uuid[-4:]}")
                        except Exception as e:
                            print(f"[Thread] ✗ {char_uuid[-4:]}: {e}")
                
                print(f"[Thread] Streaming for {duration} seconds...")
                
                # Stream for specified duration
                await asyncio.sleep(duration)
                
                # Stop notifications
                try:
                    await client.stop_notify(main_sensor)
                except:
                    pass
                
                # Halt stream
                await client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['halt'])
                
                print("[Thread] Streaming complete")
                
        except Exception as e:
            print(f"[Thread] Error: {e}")
    
    try:
        loop.run_until_complete(stream())
    finally:
        loop.close()


def main():
    """Main function"""
    print("Muse S Visualization - Windows Fix")
    print("=" * 60)
    
    # Check backends
    print("\nAvailable backends:")
    print(f"  PyQtGraph: {'Yes' if PYQTGRAPH_AVAILABLE else 'No'}")
    print(f"  Plotly/Dash: {'Yes' if PLOTLY_AVAILABLE else 'No'}")
    
    if not PYQTGRAPH_AVAILABLE:
        print("\nPyQtGraph not available!")
        return
    
    # Step 1: Find device BEFORE creating any Qt objects
    print("\nStep 1: Finding Muse device...")
    devices = scan_in_thread(timeout=5.0)
    
    if not devices:
        print("No devices found!")
        return
    
    # Select device
    if len(devices) == 1:
        device = devices[0]
        print(f"Using: {device.name}")
    else:
        print(f"\nFound {len(devices)} devices:")
        for i, d in enumerate(devices, 1):
            print(f"{i}. {d}")
        
        try:
            choice = int(input("Select device: "))
            device = devices[choice - 1]
        except:
            device = devices[0]
    
    print(f"\nSelected: {device.name}")
    print(f"Address: {device.address}")
    
    # Step 2: Create visualizer
    print("\nStep 2: Creating visualizer...")
    viz = MuseVisualizer(backend='pyqtgraph')
    
    # Step 3: Start streaming in background thread
    print("\nStep 3: Starting stream in background thread...")
    
    duration = 30  # Stream for 30 seconds
    
    stream_thread = threading.Thread(
        target=stream_in_thread,
        args=(device.address, duration, viz.visualizer),
        daemon=True
    )
    stream_thread.start()
    
    # Give thread time to connect
    time.sleep(2)
    
    # Step 4: Run visualization in main thread
    print("\nStep 4: Opening visualization window...")
    print("(Visualization will close automatically after streaming completes)")
    
    viz.run()
    
    print("\nDone!")


if __name__ == "__main__":
    try:
        # Don't set any special event loop policy
        # Let each thread manage its own loop
        main()
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()