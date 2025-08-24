"""
Example 6: Real-time Visualization (Fixed for Windows)
Stream and visualize Muse S data in real-time with interactive plots

This version fixes the Windows PyQtGraph + Bleak conflict by
scanning for devices before initializing the Qt application.
"""

import asyncio
import sys
import os
import threading
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_stream_client import MuseStreamClient
from muse_visualizer import MuseVisualizer, PYQTGRAPH_AVAILABLE, PLOTLY_AVAILABLE
from muse_discovery import find_muse_devices, select_device

# Global visualizer instance
viz = None
viz_thread = None

def process_eeg(data):
    """Process and visualize EEG data"""
    global viz
    if viz:
        viz.update_eeg(data)
    
    # Print some stats (show first available channel)
    if 'channels' in data:
        for ch_name in ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L', 'ch0']:
            samples = data['channels'].get(ch_name, [])
            if samples:
                print(f"EEG {ch_name}: {samples[0]:.1f} μV", end='\r')
                break

def process_ppg(data):
    """Process and visualize PPG data"""
    global viz
    if viz:
        viz.update_ppg(data)

def process_heart_rate(hr):
    """Process and visualize heart rate"""
    global viz
    if viz:
        viz.update_heart_rate(hr)
    print(f"Heart Rate: {hr:.0f} BPM", end='\r')

def process_imu(data):
    """Process and visualize IMU data"""
    global viz
    if viz:
        viz.update_imu(data)

async def find_device_first():
    """Find device before initializing visualization"""
    print("=" * 60)
    print("Finding Muse Device")
    print("=" * 60)
    
    print("\nSearching for Muse devices...")
    devices = await find_muse_devices(timeout=5.0)
    
    if not devices:
        print("No Muse device found!")
        print("\nMake sure your Muse S is:")
        print("1. Powered on")
        print("2. In pairing mode")
        print("3. Not connected to another device")
        return None
    
    if len(devices) == 1:
        print(f"Found: {devices[0].name}")
        return devices[0]
    else:
        print(f"Found {len(devices)} devices")
        return await select_device(devices)

async def stream_with_device(device, duration: int = 60, backend: str = 'auto'):
    """
    Stream from a specific device with visualization
    
    Args:
        device: Muse device to stream from
        duration: Streaming duration in seconds
        backend: Visualization backend
    """
    global viz, viz_thread
    
    print("=" * 60)
    print("Muse S Real-time Visualization")
    print("=" * 60)
    
    # Check available backends
    print("\nAvailable visualization backends:")
    print(f"  PyQtGraph: {'Yes' if PYQTGRAPH_AVAILABLE else 'No'}")
    print(f"  Plotly/Dash: {'Yes' if PLOTLY_AVAILABLE else 'No'}")
    
    if not (PYQTGRAPH_AVAILABLE or PLOTLY_AVAILABLE):
        print("\nNo visualization backend available!")
        print("Install one of the following:")
        print("  pip install pyqtgraph PyQt5")
        print("  pip install plotly dash")
        return
    
    # Create visualizer
    print(f"\nInitializing {backend} visualizer...")
    
    if backend == 'plotly':
        # For Plotly, we need to run in a separate thread
        viz = MuseVisualizer(backend='plotly', port=8050)
        
        def run_plotly():
            viz.run()
        
        viz_thread = threading.Thread(target=run_plotly, daemon=True)
        viz_thread.start()
        
        print("\nWeb visualization started at http://localhost:8050")
        print("Open this URL in your browser to see the visualization")
        
        # Give Plotly time to start
        await asyncio.sleep(2)
    else:
        # PyQtGraph will be initialized later
        viz = MuseVisualizer(backend='pyqtgraph')
    
    # Create streaming client
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=True
    )
    
    # Register callbacks
    print("\nRegistering visualization callbacks...")
    client.on_eeg(process_eeg)
    client.on_ppg(process_ppg)
    client.on_heart_rate(process_heart_rate)
    client.on_imu(process_imu)
    
    # Start streaming
    print(f"\nStarting {duration}-second streaming session...")
    print("Visualization will update in real-time\n")
    
    if backend == 'pyqtgraph':
        # For PyQtGraph, stream in background thread
        async def stream_task():
            await client.connect_and_stream(
                device.address,
                duration_seconds=duration,
                preset='p1034'  # Full sensor suite
            )
        
        # Start streaming in background
        stream_thread = threading.Thread(
            target=lambda: asyncio.run(stream_task()),
            daemon=True
        )
        stream_thread.start()
        
        # Run PyQtGraph in main thread
        print("Opening visualization window...")
        viz.run()
    else:
        # For Plotly, just stream normally
        success = await client.connect_and_stream(
            device.address,
            duration_seconds=duration,
            preset='p1034'
        )
        
        if success:
            print("\nStreaming complete!")
            summary = client.get_summary()
            print(f"Total packets: {summary['packets_received']}")
            
            if backend == 'plotly':
                print("\nVisualization remains open at http://localhost:8050")
                print("Press Ctrl+C to stop the server")
                
                # Keep server running
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    print("\nStopping visualization server...")

async def main():
    """Main example function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Muse S Real-time Visualization')
    parser.add_argument('--backend', choices=['pyqtgraph', 'plotly', 'auto'], default='auto',
                       help='Visualization backend')
    parser.add_argument('--duration', type=int, default=60,
                       help='Streaming duration in seconds')
    
    args = parser.parse_args()
    
    print("Amused Real-time Visualization Example")
    print("=" * 60)
    print(f"Backend: {args.backend}")
    print(f"Duration: {args.duration} seconds")
    print()
    
    # IMPORTANT: Find device BEFORE initializing PyQtGraph
    # This avoids the Windows event loop conflict
    device = await find_device_first()
    
    if not device:
        print("\nNo device selected. Exiting.")
        return
    
    print(f"\nSelected: {device.name}")
    print(f"Address: {device.address}")
    
    # Now stream with visualization
    await stream_with_device(device, args.duration, args.backend)

if __name__ == "__main__":
    try:
        # For Windows, we handle the event loop carefully
        if sys.platform == 'win32':
            # Don't set WindowsSelectorEventLoopPolicy for PyQtGraph
            # Let it use the default ProactorEventLoop
            pass
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nVisualization stopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()