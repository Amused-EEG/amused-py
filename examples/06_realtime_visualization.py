"""
Example 6: Real-time Visualization
Stream and visualize Muse S data in real-time with interactive plots

Features:
- Live EEG waveforms (7 channels: TP9, AF7, AF8, TP10, FPz, AUX_R, AUX_L)
- PPG heart rate monitoring
- IMU motion tracking
- Frequency spectrum analysis
- Multiple visualization backends
"""

import asyncio
import sys
import os
import threading
from datetime import datetime

# Fix Windows Qt/Bleak conflict BEFORE any other imports
try:
    from bleak.backends.winrt.util import allow_sta
    allow_sta()  # Tell Bleak we're using a GUI that works with asyncio
except ImportError:
    pass  # Not Windows or older Bleak version

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_stream_client import MuseStreamClient
from muse_visualizer import MuseVisualizer, PYQTGRAPH_AVAILABLE, PLOTLY_AVAILABLE

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

async def stream_with_visualization(duration: int = 60, backend: str = 'auto', device_address: str = None):
    """
    Stream Muse data with real-time visualization
    
    Args:
        duration: Streaming duration in seconds
        backend: Visualization backend ('pyqtgraph', 'plotly', or 'auto')
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
        # PyQtGraph runs in the main thread after streaming setup
        viz = MuseVisualizer(backend='pyqtgraph')
    
    # Create streaming client
    client = MuseStreamClient(
        save_raw=False,  # Don't save, just visualize
        decode_realtime=True,
        verbose=True
    )
    
    # Register callbacks
    print("\nRegistering visualization callbacks...")
    client.on_eeg(process_eeg)
    client.on_ppg(process_ppg)
    client.on_heart_rate(process_heart_rate)
    client.on_imu(process_imu)
    
    # Find device
    print("\nSearching for Muse device...")
    device = await client.find_device()
    
    if not device:
        print("No Muse device found!")
        print("\nMake sure your Muse S is:")
        print("1. Powered on")
        print("2. In pairing mode")
        print("3. Not connected to another device")
        return
    
    print(f"Found: {device.name}")
    device_address = device.address
    
    # Start streaming in background
    print(f"\nStarting {duration}-second streaming session...")
    print("Visualization will update in real-time\n")
    
    if backend == 'pyqtgraph':
        # With allow_sta() fix, we can run BLE in a simpler way
        async def stream_task():
            await client.connect_and_stream(
                device_address,
                duration_seconds=duration,
                preset='p1035'  # Sleep mode with ALL sensors
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
            device_address,
            duration_seconds=duration,
            preset='p1035'  # Sleep mode with ALL sensors
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

async def replay_with_visualization(filepath: str = None, backend: str = 'auto'):
    """
    Replay recorded data with visualization
    
    Args:
        filepath: Path to binary recording file
        backend: Visualization backend
    """
    global viz
    
    print("=" * 60)
    print("Replay with Visualization")
    print("=" * 60)
    
    if not filepath:
        # Find most recent recording
        import glob
        recordings = glob.glob("muse_data/*.bin") + glob.glob("test_data/*.bin")
        if not recordings:
            print("No recordings found!")
            print("Record some data first using examples 02 or 05")
            return
        filepath = max(recordings, key=os.path.getctime)
    
    print(f"Replaying: {filepath}")
    
    # Create visualizer
    viz = MuseVisualizer(backend=backend)
    
    # Import replay module
    from muse_replay import MuseReplayPlayer
    
    # Create replay player
    player = MuseReplayPlayer(
        filepath=filepath,
        speed=1.0,  # Real-time playback
        decode=True,
        verbose=True
    )
    
    # Register callbacks
    def on_decoded(data):
        if data.eeg:
            viz.update_eeg({'channels': data.eeg, 'timestamp': data.timestamp.timestamp()})
        if data.ppg:
            viz.update_ppg({'samples': data.ppg.get('samples', []), 'timestamp': data.timestamp.timestamp()})
        if data.heart_rate:
            viz.update_heart_rate(data.heart_rate)
        if data.imu:
            viz.update_imu({'accel': data.imu.get('accel', []), 'gyro': data.imu.get('gyro', []), 'timestamp': data.timestamp.timestamp()})
    
    player.on_decoded(on_decoded)
    
    # Get info
    info = player.get_info()
    print(f"Duration: {info['duration_seconds']:.1f} seconds")
    print(f"Packets: {info['total_packets']}")
    
    if backend == 'pyqtgraph':
        # Start replay in background
        async def replay_task():
            await player.play(realtime=True)
        
        replay_thread = threading.Thread(
            target=lambda: asyncio.run(replay_task()),
            daemon=True
        )
        replay_thread.start()
        
        # Run visualization
        print("\nOpening visualization window...")
        viz.run()
    else:
        # For Plotly
        viz_thread = threading.Thread(target=viz.run, daemon=True)
        viz_thread.start()
        
        print("\nWeb visualization at http://localhost:8050")
        await asyncio.sleep(2)
        
        # Play recording
        await player.play(realtime=True)
        
        print("\nReplay complete!")
        print("Visualization remains open. Press Ctrl+C to exit")
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

async def main():
    """Main example function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Muse S Real-time Visualization')
    parser.add_argument('--mode', choices=['stream', 'replay'], default='stream',
                       help='Visualization mode: stream (live) or replay (recorded)')
    parser.add_argument('--backend', choices=['pyqtgraph', 'plotly', 'auto'], default='auto',
                       help='Visualization backend')
    parser.add_argument('--duration', type=int, default=60,
                       help='Streaming duration in seconds')
    parser.add_argument('--file', type=str, default=None,
                       help='Binary file to replay')
    
    args = parser.parse_args()
    
    print("Amused Real-time Visualization Example")
    print("=" * 60)
    print(f"Mode: {args.mode}")
    print(f"Backend: {args.backend}")
    
    if args.mode == 'stream':
        await stream_with_visualization(args.duration, args.backend)
    else:
        await replay_with_visualization(args.file, args.backend)

if __name__ == "__main__":
    try:
        # For Windows with PyQtGraph, we need special handling
        if sys.platform == 'win32':
            # Check if PyQtGraph will be used
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument('--backend', default='auto')
            args, _ = parser.parse_known_args()
            
            if args.backend in ['pyqtgraph', 'auto']:
                # Use default policy for PyQtGraph
                pass
            else:
                # Use selector for other backends
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nVisualization stopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()