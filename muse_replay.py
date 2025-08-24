"""
Muse Binary Replay System
Replay saved binary data as if it were streaming in real-time

Perfect for:
- Offline analysis with real-time processing pipelines
- Testing algorithms without device connection
- Sharing datasets that can be replayed exactly
"""

import asyncio
import datetime
import time
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass
import os

from muse_raw_stream import MuseRawStream, RawPacket
from muse_realtime_decoder import MuseRealtimeDecoder, DecodedData

class MuseReplayPlayer:
    """
    Replay binary recordings with real-time simulation
    
    Features:
    - Accurate timing reproduction
    - Speed control (1x, 2x, 0.5x, etc.)
    - Seek to specific time
    - Pause/resume
    - Same callback interface as live streaming
    """
    
    def __init__(self, 
                 filepath: str,
                 speed: float = 1.0,
                 decode: bool = True,
                 verbose: bool = True):
        """
        Initialize replay player
        
        Args:
            filepath: Path to binary recording
            speed: Playback speed (1.0 = real-time, 2.0 = 2x speed)
            decode: Enable real-time decoding
            verbose: Print status messages
        """
        self.filepath = filepath
        self.speed = speed
        self.decode = decode
        self.verbose = verbose
        
        # Verify file exists
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Recording not found: {filepath}")
        
        # Stream handler
        self.stream = MuseRawStream(filepath)
        
        # Decoder
        self.decoder = MuseRealtimeDecoder() if decode else None
        
        # Playback state
        self.is_playing = False
        self.is_paused = False
        self.current_packet_num = 0
        self.start_time = None
        self.pause_time = None
        self.total_pause_duration = 0
        
        # Load packet index for seeking
        self.packet_index: List[RawPacket] = []
        self._build_packet_index()
        
        # Statistics
        self.stats = {
            'packets_played': 0,
            'playback_time': 0,
            'actual_time': 0
        }
        
        # Callbacks
        self.callbacks = {
            'packet': [],      # Raw packet callbacks
            'decoded': [],     # Decoded data callbacks
            'progress': [],    # Progress update callbacks
            'complete': []     # Playback complete callbacks
        }
    
    def _build_packet_index(self):
        """Build index of all packets for seeking"""
        self.log("Building packet index...")
        
        self.stream.open_read()
        for packet in self.stream.read_packets():
            self.packet_index.append(packet)
        self.stream.close()
        
        if self.packet_index:
            self.duration = (self.packet_index[-1].timestamp - self.packet_index[0].timestamp).total_seconds()
            self.log(f"Loaded {len(self.packet_index)} packets, duration: {self.duration:.1f} seconds")
        else:
            self.duration = 0
            self.log("No packets found in file")
    
    def on_packet(self, callback: Callable[[bytes, datetime.datetime], None]):
        """Register callback for raw packets"""
        self.callbacks['packet'].append(callback)
    
    def on_decoded(self, callback: Callable[[DecodedData], None]):
        """Register callback for decoded data"""
        self.callbacks['decoded'].append(callback)
        
    def on_progress(self, callback: Callable[[float], None]):
        """Register callback for playback progress (0.0 to 1.0)"""
        self.callbacks['progress'].append(callback)
    
    def on_complete(self, callback: Callable[[], None]):
        """Register callback for playback completion"""
        self.callbacks['complete'].append(callback)
    
    def log(self, message: str):
        """Log message with timestamp"""
        if self.verbose:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[REPLAY {timestamp}] {message}")
    
    async def play(self, 
                   start_time: float = 0,
                   duration: Optional[float] = None,
                   realtime: bool = True):
        """
        Play recording
        
        Args:
            start_time: Start position in seconds
            duration: Playback duration in seconds (None = entire recording)
            realtime: Simulate real-time delays between packets
        """
        if self.is_playing:
            self.log("Already playing")
            return
        
        self.is_playing = True
        self.is_paused = False
        self.current_packet_num = 0
        self.stats['packets_played'] = 0
        
        # Find start packet
        start_packet_idx = 0
        if start_time > 0:
            for i, packet in enumerate(self.packet_index):
                if (packet.timestamp - self.packet_index[0].timestamp).total_seconds() >= start_time:
                    start_packet_idx = i
                    break
        
        # Calculate end packet
        end_packet_idx = len(self.packet_index)
        if duration:
            target_end_time = start_time + duration
            for i, packet in enumerate(self.packet_index[start_packet_idx:], start_packet_idx):
                if (packet.timestamp - self.packet_index[0].timestamp).total_seconds() >= target_end_time:
                    end_packet_idx = i
                    break
        
        self.log(f"Playing packets {start_packet_idx} to {end_packet_idx}")
        self.log(f"Speed: {self.speed}x, Real-time: {realtime}")
        
        # Start playback
        playback_start = time.perf_counter()
        first_packet_time = self.packet_index[start_packet_idx].timestamp if start_packet_idx < len(self.packet_index) else None
        
        for i in range(start_packet_idx, end_packet_idx):
            if not self.is_playing:
                break
            
            # Handle pause
            while self.is_paused:
                await asyncio.sleep(0.01)
            
            packet = self.packet_index[i]
            self.current_packet_num = i
            
            # Simulate real-time delay
            if realtime and i > start_packet_idx:
                # Calculate time since start
                packet_time_offset = (packet.timestamp - first_packet_time).total_seconds()
                playback_elapsed = (time.perf_counter() - playback_start) * self.speed
                
                # Wait if we're ahead of schedule
                wait_time = (packet_time_offset - playback_elapsed) / self.speed
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            
            # Trigger packet callbacks
            for callback in self.callbacks['packet']:
                callback(packet.data, packet.timestamp)
            
            # Decode if enabled
            if self.decode and self.decoder:
                decoded = self.decoder.decode(packet.data, packet.timestamp)
                
                # Trigger decoded callbacks
                for callback in self.callbacks['decoded']:
                    callback(decoded)
            
            # Update statistics
            self.stats['packets_played'] += 1
            
            # Progress updates every 100 packets
            if i % 100 == 0:
                progress = (i - start_packet_idx) / (end_packet_idx - start_packet_idx)
                for callback in self.callbacks['progress']:
                    callback(progress)
                
                if self.verbose and i % 1000 == 0:
                    self.log(f"Progress: {progress:.1%} ({i}/{end_packet_idx} packets)")
        
        # Playback complete
        self.is_playing = False
        self.log(f"Playback complete: {self.stats['packets_played']} packets")
        
        # Trigger completion callbacks
        for callback in self.callbacks['complete']:
            callback()
    
    def pause(self):
        """Pause playback"""
        if self.is_playing and not self.is_paused:
            self.is_paused = True
            self.pause_time = time.perf_counter()
            self.log("Paused")
    
    def resume(self):
        """Resume playback"""
        if self.is_paused:
            self.total_pause_duration += time.perf_counter() - self.pause_time
            self.is_paused = False
            self.log("Resumed")
    
    def stop(self):
        """Stop playback"""
        self.is_playing = False
        self.is_paused = False
        self.log("Stopped")
    
    def seek(self, time_seconds: float):
        """
        Seek to specific time (requires restart)
        
        Args:
            time_seconds: Target time in seconds
        """
        # Find closest packet
        for i, packet in enumerate(self.packet_index):
            if (packet.timestamp - self.packet_index[0].timestamp).total_seconds() >= time_seconds:
                self.current_packet_num = i
                self.log(f"Seeked to {time_seconds:.1f}s (packet {i})")
                return
    
    def set_speed(self, speed: float):
        """
        Set playback speed
        
        Args:
            speed: Playback speed (1.0 = normal, 2.0 = 2x, 0.5 = half)
        """
        self.speed = speed
        self.log(f"Speed set to {speed}x")
    
    def get_info(self) -> Dict[str, Any]:
        """Get replay information"""
        return {
            'filepath': self.filepath,
            'total_packets': len(self.packet_index),
            'duration_seconds': self.duration,
            'current_packet': self.current_packet_num,
            'progress': self.current_packet_num / max(1, len(self.packet_index)),
            'is_playing': self.is_playing,
            'is_paused': self.is_paused,
            'speed': self.speed,
            'packets_played': self.stats['packets_played']
        }

class MuseBinaryParser:
    """
    Parse and analyze binary recordings without replay
    
    For batch processing and analysis
    """
    
    def __init__(self, filepath: str):
        """Initialize parser"""
        self.filepath = filepath
        self.stream = MuseRawStream(filepath)
        self.decoder = MuseRealtimeDecoder()
    
    def parse_all(self) -> Dict[str, Any]:
        """
        Parse entire file and return statistics
        
        Returns:
            Dictionary with parsed data and statistics
        """
        results = {
            'eeg_data': [],
            'ppg_data': [],
            'imu_data': [],
            'heart_rates': [],
            'timestamps': [],
            'packet_types': {},
            'duration': 0,
            'total_packets': 0
        }
        
        self.stream.open_read()
        first_timestamp = None
        last_timestamp = None
        
        for packet in self.stream.read_packets():
            if first_timestamp is None:
                first_timestamp = packet.timestamp
            last_timestamp = packet.timestamp
            
            # Decode packet
            decoded = self.decoder.decode(packet.data, packet.timestamp)
            
            # Store results
            results['timestamps'].append(packet.timestamp)
            results['total_packets'] += 1
            
            # Track packet types
            ptype = decoded.packet_type
            results['packet_types'][ptype] = results['packet_types'].get(ptype, 0) + 1
            
            # Store sensor data
            if decoded.eeg:
                results['eeg_data'].append({
                    'timestamp': packet.timestamp,
                    'channels': decoded.eeg
                })
            
            if decoded.ppg:
                results['ppg_data'].append({
                    'timestamp': packet.timestamp,
                    'samples': decoded.ppg
                })
            
            if decoded.imu:
                results['imu_data'].append({
                    'timestamp': packet.timestamp,
                    'accel': decoded.imu.get('accel'),
                    'gyro': decoded.imu.get('gyro')
                })
            
            if decoded.heart_rate:
                results['heart_rates'].append({
                    'timestamp': packet.timestamp,
                    'bpm': decoded.heart_rate
                })
        
        self.stream.close()
        
        # Calculate duration
        if first_timestamp and last_timestamp:
            results['duration'] = (last_timestamp - first_timestamp).total_seconds()
        
        # Get decoder statistics
        stats = self.decoder.get_stats()
        results['decoder_stats'] = stats
        
        return results
    
    def extract_time_range(self, start_seconds: float, end_seconds: float) -> List[RawPacket]:
        """
        Extract packets from specific time range
        
        Args:
            start_seconds: Start time in seconds
            end_seconds: End time in seconds
            
        Returns:
            List of packets in time range
        """
        packets = []
        
        self.stream.open_read()
        first_timestamp = None
        
        for packet in self.stream.read_packets():
            if first_timestamp is None:
                first_timestamp = packet.timestamp
            
            elapsed = (packet.timestamp - first_timestamp).total_seconds()
            
            if elapsed >= start_seconds and elapsed <= end_seconds:
                packets.append(packet)
            elif elapsed > end_seconds:
                break
        
        self.stream.close()
        return packets

# Example usage
async def example_replay():
    """Example of replaying a recording"""
    
    print("Muse Replay Example")
    print("=" * 60)
    
    # Find a recording
    import glob
    recordings = glob.glob("muse_data/*.bin") + glob.glob("raw_data/*.bin")
    
    if not recordings:
        print("No recordings found. Run muse_stream_client.py first.")
        return
    
    # Use most recent recording
    recording = max(recordings, key=os.path.getctime)
    print(f"Replaying: {recording}")
    
    # Create player
    player = MuseReplayPlayer(recording, speed=2.0)  # 2x speed
    
    # Register callbacks
    def on_eeg(data: DecodedData):
        if data.eeg:
            print(f"EEG: {len(data.eeg)} channels")
    
    def on_heart_rate(data: DecodedData):
        if data.heart_rate:
            print(f"Heart Rate: {data.heart_rate:.0f} BPM")
    
    def on_progress(progress: float):
        print(f"Progress: {progress:.1%}")
    
    player.on_decoded(on_eeg)
    player.on_decoded(on_heart_rate)
    player.on_progress(on_progress)
    
    # Play recording
    await player.play(start_time=0, duration=10, realtime=True)
    
    # Show info
    info = player.get_info()
    print(f"\nReplay complete!")
    print(f"Packets played: {info['packets_played']}")
    print(f"Duration: {info['duration_seconds']:.1f} seconds")

def example_parse():
    """Example of parsing without replay"""
    
    print("Binary Parser Example")
    print("=" * 60)
    
    # Find a recording
    import glob
    recordings = glob.glob("muse_data/*.bin") + glob.glob("raw_data/*.bin")
    
    if not recordings:
        print("No recordings found.")
        return
    
    recording = recordings[0]
    print(f"Parsing: {recording}")
    
    # Parse file
    parser = MuseBinaryParser(recording)
    results = parser.parse_all()
    
    print(f"\nResults:")
    print(f"  Duration: {results['duration']:.1f} seconds")
    print(f"  Total packets: {results['total_packets']}")
    print(f"  Packet types: {results['packet_types']}")
    print(f"  EEG samples: {len(results['eeg_data'])}")
    print(f"  Heart rate measurements: {len(results['heart_rates'])}")
    
    if results['heart_rates']:
        avg_hr = sum(h['bpm'] for h in results['heart_rates']) / len(results['heart_rates'])
        print(f"  Average heart rate: {avg_hr:.0f} BPM")

if __name__ == "__main__":
    # Run replay example
    asyncio.run(example_replay())
    
    # Run parse example
    print("\n")
    example_parse()