"""
Example 6: Real-time Visualization (Proper Windows Fix)
Uses asyncio.run_coroutine_threadsafe for proper Qt/asyncio integration

This is the fancy visualization with all sensors working properly on Windows!
"""

import asyncio
import sys
import os
import threading
import queue
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows conflict FIRST
try:
    from bleak.backends.winrt.util import allow_sta
    allow_sta()
except ImportError:
    pass

from muse_stream_client import MuseStreamClient
from muse_visualizer import MuseVisualizer, PYQTGRAPH_AVAILABLE, PLOTLY_AVAILABLE
from muse_discovery import find_muse_devices, select_device

# Global for data passing
data_queue = queue.Queue()
status_queue = queue.Queue()

def process_eeg(data):
    """Process and visualize EEG data"""
    data_queue.put(('eeg', data))
    
    if 'channels' in data:
        for ch_name in ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']:
            samples = data['channels'].get(ch_name, [])
            if samples:
                status_queue.put(f"EEG {ch_name}: {samples[0]:.1f} uV")
                break

def process_ppg(data):
    """Process and visualize PPG data"""
    data_queue.put(('ppg', data))

def process_heart_rate(hr):
    """Process and visualize heart rate"""
    data_queue.put(('heart_rate', hr))
    status_queue.put(f"Heart Rate: {hr:.0f} BPM")

def process_imu(data):
    """Process and visualize IMU data"""
    data_queue.put(('imu', data))

async def stream_worker(device_address: str, duration: int):
    """Worker coroutine for streaming"""
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=True
    )
    
    # Register callbacks
    client.on_eeg(process_eeg)
    client.on_ppg(process_ppg)
    client.on_heart_rate(process_heart_rate)
    client.on_imu(process_imu)
    
    # Connect and stream using SLEEP MODE for all sensors
    print(f"[Async] Connecting to {device_address}...")
    success = await client.connect_and_stream(
        device_address,
        duration_seconds=duration,
        preset='p1035'  # Sleep mode with ALL sensors (EEG + PPG + fNIRS + IMU)
    )
    
    if success:
        print("[Async] Streaming complete!")
        summary = client.get_summary()
        status_queue.put(f"Complete! Total packets: {summary['packets_received']}")
    else:
        print("[Async] Streaming failed")
        status_queue.put("Streaming failed")

def run_async_loop(device_address: str, duration: int):
    """Run async event loop in thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(stream_worker(device_address, duration))
    finally:
        loop.close()

def update_viz_from_queue(viz):
    """Update visualizer from queue (called by Qt timer)"""
    # Process up to 10 items per update to avoid blocking
    for _ in range(10):
        try:
            data_type, data = data_queue.get_nowait()
            
            if data_type == 'eeg':
                viz.update_eeg(data)
            elif data_type == 'ppg':
                viz.update_ppg(data)
            elif data_type == 'heart_rate':
                viz.update_heart_rate(data)
            elif data_type == 'imu':
                viz.update_imu(data)
        except queue.Empty:
            break
    
    # Update status
    try:
        status = status_queue.get_nowait()
        # Avoid unicode issues on Windows console
        print(status.replace('μ', 'u'), end='\r')
    except queue.Empty:
        pass

def main():
    """Main function"""
    print("Muse S Real-time Visualization (Fancy Edition)")
    print("=" * 60)
    
    # Check backends
    print("\nAvailable visualization backends:")
    print(f"  PyQtGraph: {'Yes' if PYQTGRAPH_AVAILABLE else 'No'}")
    print(f"  Plotly/Dash: {'Yes' if PLOTLY_AVAILABLE else 'No'}")
    
    if not PYQTGRAPH_AVAILABLE:
        print("\nPyQtGraph not available!")
        print("Install with: pip install pyqtgraph PyQt5")
        return
    
    # Step 1: Find device BEFORE Qt initialization
    print("\n" + "=" * 60)
    print("Step 1: Device Discovery")
    print("=" * 60)
    
    print("\nSearching for Muse devices...")
    
    # Run discovery in async context
    async def discover():
        return await find_muse_devices(timeout=5.0)
    
    devices = asyncio.run(discover())
    
    if not devices:
        print("No Muse devices found!")
        print("\nMake sure your Muse S is:")
        print("1. Powered on")
        print("2. In pairing mode (hold power button)")
        print("3. Not connected to another device")
        return
    
    # Select device
    if len(devices) == 1:
        device = devices[0]
        print(f"Found: {device.name}")
    else:
        print(f"\nFound {len(devices)} devices:")
        for i, d in enumerate(devices, 1):
            print(f"{i}. {d}")
        
        # Let user select
        async def select():
            return await select_device(devices)
        
        device = asyncio.run(select())
        if not device:
            print("No device selected")
            return
    
    print(f"\nSelected: {device.name}")
    print(f"Address: {device.address}")
    
    # Step 2: Create visualizer
    print("\n" + "=" * 60)
    print("Step 2: Initialize Visualization")
    print("=" * 60)
    
    print("\nCreating fancy visualizer...")
    viz = MuseVisualizer(
        backend='pyqtgraph',
        window_size=2560  # 10 seconds at 256 Hz
    )
    
    # Setup update timer for Qt
    from PyQt5.QtCore import QTimer
    timer = QTimer()
    timer.timeout.connect(lambda: update_viz_from_queue(viz.visualizer))
    timer.start(67)  # 15 Hz update for less lag
    
    # Step 3: Start streaming in background thread
    print("\n" + "=" * 60)
    print("Step 3: Start Streaming")
    print("=" * 60)
    
    duration = 300  # Stream for 5 minutes
    print(f"\nStarting {duration}-second streaming session...")
    print("Using SLEEP MODE preset for ALL sensors:")
    print("  - 7 EEG channels (TP9, AF7, AF8, TP10, FPz, AUX_R, AUX_L)")
    print("  - PPG heart rate (3 wavelengths)")
    print("  - fNIRS blood oxygenation")
    print("  - IMU motion (accelerometer + gyroscope)")
    
    # Start async streaming in background thread
    stream_thread = threading.Thread(
        target=run_async_loop,
        args=(device.address, duration),
        daemon=True
    )
    stream_thread.start()
    
    # Step 4: Run visualization
    print("\n" + "=" * 60)
    print("Step 4: Opening Visualization Window")
    print("=" * 60)
    
    print("\nVisualization window opening...")
    print("Data will appear once streaming starts")
    print("Close window to stop\n")
    
    # Run Qt event loop
    viz.run()
    
    print("\n\nVisualization closed")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()