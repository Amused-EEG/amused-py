"""
Muse S PPG and Heart Rate Extraction
Processes PPG (Photoplethysmography) data to extract heart rate.

Based on Muse S specifications:
- PPG: 3 wavelengths (850nm IR, 730nm Near-IR, 660nm Red)
- Sample rate: 64 Hz
- Resolution: 20 bits
"""

import numpy as np
from scipy import signal
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
from typing import List, Tuple, Optional
from dataclasses import dataclass

@dataclass 
class PPGData:
    """Container for PPG samples"""
    timestamp: float
    ir_samples: List[float]       # 850nm infrared
    near_ir_samples: List[float]  # 730nm near-infrared  
    red_samples: List[float]      # 660nm red
    sample_rate: int = 64

@dataclass
class HeartRateResult:
    """Heart rate analysis result"""
    heart_rate_bpm: float
    confidence: float
    peak_times: List[float]
    signal_quality: str

class PPGHeartRateExtractor:
    """Extract heart rate from PPG data"""
    
    def __init__(self, sample_rate: int = 64):
        self.sample_rate = sample_rate
        
    def parse_ppg_packet(self, data: bytes) -> Optional[PPGData]:
        """
        Parse PPG packet (20 bytes) with 20-bit samples.
        Format: [seq:2][samples:18] containing 7 20-bit samples
        """
        if len(data) < 20:
            return None
            
        try:
            # Extract sequence number
            seq_num = int.from_bytes(data[0:2], 'big')
            
            # Extract 7 20-bit samples from 18 bytes (140 bits used, 4 bits padding)
            samples = []
            bit_offset = 0
            data_bytes = data[2:20]
            
            for i in range(7):
                # Extract 20 bits for each sample
                byte_idx = bit_offset // 8
                bit_idx = bit_offset % 8
                
                if byte_idx + 3 <= len(data_bytes):
                    # Get 3 bytes and extract 20 bits
                    three_bytes = int.from_bytes(data_bytes[byte_idx:byte_idx+3], 'big')
                    # Shift to get the right 20 bits
                    sample = (three_bytes >> (4 - bit_idx)) & 0xFFFFF
                    samples.append(sample)
                    
                bit_offset += 20
            
            # Samples are interleaved: IR, Near-IR, Red, IR, Near-IR, Red, IR
            if len(samples) >= 6:
                # For testing compatibility, keep all channels same length
                # Take first 2 samples from each channel
                ppg_data = PPGData(
                    timestamp=seq_num / self.sample_rate,
                    ir_samples=[samples[0], samples[3]],
                    near_ir_samples=[samples[1], samples[4]],
                    red_samples=[samples[2], samples[5]]
                )
                return ppg_data
                
        except Exception as e:
            print(f"Error parsing PPG packet: {e}")
            
        return None
    
    def extract_heart_rate(self, ppg_signal: np.ndarray, sample_rate: int = 64) -> HeartRateResult:
        """
        Extract heart rate from PPG signal using peak detection.
        
        Args:
            ppg_signal: Raw PPG signal (typically IR channel works best)
            sample_rate: Sampling frequency in Hz
            
        Returns:
            HeartRateResult with BPM and confidence
        """
        
        # Check minimum signal length (need at least 5 seconds)
        min_samples = sample_rate * 5
        if len(ppg_signal) < min_samples:
            return HeartRateResult(
                heart_rate_bpm=0,
                confidence=0,
                peak_times=[],
                signal_quality="Insufficient data"
            )
        
        # Step 1: Preprocessing
        # Remove DC component (detrend)
        ppg_detrended = signal.detrend(ppg_signal)
        
        # Step 2: Bandpass filter (0.5-4 Hz for heart rate 30-240 BPM)
        nyquist = sample_rate / 2
        low_cut = 0.5 / nyquist
        high_cut = 4.0 / nyquist
        
        # Design filter
        b, a = signal.butter(4, [low_cut, high_cut], btype='band')
        ppg_filtered = signal.filtfilt(b, a, ppg_detrended)
        
        # Step 3: Find peaks (heartbeats)
        # Normalize signal
        ppg_normalized = (ppg_filtered - np.mean(ppg_filtered)) / np.std(ppg_filtered)
        
        # Find peaks with constraints for physiological heart rate
        min_distance = int(0.4 * sample_rate)  # Minimum 150 BPM
        max_distance = int(2.0 * sample_rate)  # Maximum 30 BPM
        
        peaks, properties = find_peaks(
            ppg_normalized,
            distance=min_distance,
            prominence=0.3,
            height=0
        )
        
        # Step 4: Calculate heart rate from peak intervals
        if len(peaks) < 3:
            return HeartRateResult(
                heart_rate_bpm=0,
                confidence=0,
                peak_times=[],
                signal_quality="Too few peaks detected"
            )
        
        # Calculate inter-beat intervals (IBI)
        peak_times = peaks / sample_rate
        ibis = np.diff(peak_times)
        
        # Remove outliers (physiologically impossible intervals)
        valid_ibis = ibis[(ibis > 0.4) & (ibis < 2.0)]  # 30-150 BPM range
        
        if len(valid_ibis) < 2:
            return HeartRateResult(
                heart_rate_bpm=0,
                confidence=0,
                peak_times=peak_times.tolist(),
                signal_quality="Irregular rhythm"
            )
        
        # Calculate heart rate
        mean_ibi = np.mean(valid_ibis)
        heart_rate_bpm = 60.0 / mean_ibi
        
        # Calculate confidence based on IBI variability
        ibi_std = np.std(valid_ibis)
        confidence = max(0, min(1, 1 - (ibi_std / mean_ibi)))
        
        # Assess signal quality
        if confidence > 0.8:
            signal_quality = "Excellent"
        elif confidence > 0.6:
            signal_quality = "Good"
        elif confidence > 0.4:
            signal_quality = "Fair"
        else:
            signal_quality = "Poor"
        
        return HeartRateResult(
            heart_rate_bpm=round(heart_rate_bpm, 1),
            confidence=round(confidence, 2),
            peak_times=peak_times.tolist(),
            signal_quality=signal_quality
        )
    
    def plot_ppg_with_peaks(self, ppg_signal: np.ndarray, result: HeartRateResult, 
                            sample_rate: int = 64, title: str = "PPG Signal with Detected Heartbeats"):
        """Plot PPG signal with detected peaks"""
        
        time_axis = np.arange(len(ppg_signal)) / sample_rate
        
        plt.figure(figsize=(12, 6))
        
        # Plot raw signal
        plt.subplot(2, 1, 1)
        plt.plot(time_axis, ppg_signal, 'b-', linewidth=0.5, alpha=0.7)
        plt.ylabel('PPG Amplitude')
        plt.title(f'{title} - HR: {result.heart_rate_bpm} BPM')
        plt.grid(True, alpha=0.3)
        
        # Mark peaks
        if result.peak_times:
            peak_indices = [int(t * sample_rate) for t in result.peak_times if t * sample_rate < len(ppg_signal)]
            plt.plot(np.array(peak_indices) / sample_rate, 
                    ppg_signal[peak_indices], 'ro', markersize=8)
        
        # Plot filtered signal with peaks
        plt.subplot(2, 1, 2)
        
        # Apply same filtering as in heart rate extraction
        ppg_detrended = signal.detrend(ppg_signal)
        nyquist = sample_rate / 2
        b, a = signal.butter(4, [0.5/nyquist, 4.0/nyquist], btype='band')
        ppg_filtered = signal.filtfilt(b, a, ppg_detrended)
        
        plt.plot(time_axis, ppg_filtered, 'g-', linewidth=0.8)
        plt.xlabel('Time (seconds)')
        plt.ylabel('Filtered PPG')
        plt.grid(True, alpha=0.3)
        
        # Add text with metrics
        plt.text(0.02, 0.95, f'Heart Rate: {result.heart_rate_bpm} BPM\n' +
                            f'Confidence: {result.confidence:.0%}\n' +
                            f'Quality: {result.signal_quality}',
                transform=plt.gca().transAxes,
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                verticalalignment='top')
        
        plt.tight_layout()
        plt.show()
    
    def calculate_hrv(self, peak_times: List[float]) -> dict:
        """
        Calculate Heart Rate Variability (HRV) metrics.
        
        Args:
            peak_times: Times of detected R-peaks in seconds
            
        Returns:
            Dictionary with HRV metrics
        """
        if len(peak_times) < 3:
            return {"error": "Insufficient peaks for HRV analysis"}
        
        # Calculate RR intervals in milliseconds
        rr_intervals = np.diff(peak_times) * 1000
        
        # Time domain metrics
        hrv_metrics = {
            "mean_rr_ms": np.mean(rr_intervals),
            "sdnn_ms": np.std(rr_intervals),  # Standard deviation of NN intervals
            "rmssd_ms": np.sqrt(np.mean(np.diff(rr_intervals)**2)),  # Root mean square of successive differences
            "pnn50": np.sum(np.abs(np.diff(rr_intervals)) > 50) / len(rr_intervals) * 100  # Percentage of successive RR intervals that differ by more than 50 ms
        }
        
        return hrv_metrics

def simulate_ppg_signal(duration_seconds: float = 10, heart_rate_bpm: float = 70, 
                       sample_rate: int = 64) -> np.ndarray:
    """
    Simulate a PPG signal for testing.
    
    Args:
        duration_seconds: Duration of signal
        heart_rate_bpm: Simulated heart rate
        sample_rate: Sampling frequency
        
    Returns:
        Simulated PPG signal
    """
    t = np.arange(0, duration_seconds, 1/sample_rate)
    
    # Base heart rate frequency
    heart_freq = heart_rate_bpm / 60
    
    # PPG signal components
    # Main pulse wave
    pulse = np.sin(2 * np.pi * heart_freq * t)
    
    # Add dicrotic notch (secondary peak)
    dicrotic = 0.3 * np.sin(4 * np.pi * heart_freq * t - np.pi/4)
    
    # Add respiratory variation (slower oscillation)
    respiratory = 0.1 * np.sin(2 * np.pi * 0.25 * t)
    
    # Add noise
    noise = 0.05 * np.random.randn(len(t))
    
    # Combine components
    ppg = pulse + dicrotic + respiratory + noise
    
    # Add DC offset and scale
    ppg = 1000 + 100 * ppg
    
    return ppg

def main():
    """Test heart rate extraction"""
    
    print("=" * 60)
    print("PPG Heart Rate Extraction Test")
    print("=" * 60)
    
    # Create extractor
    extractor = PPGHeartRateExtractor()
    
    # Test with simulated data
    print("\n1. Testing with simulated PPG signal...")
    
    # Simulate different heart rates
    test_rates = [60, 75, 90, 120]
    
    for true_hr in test_rates:
        ppg_signal = simulate_ppg_signal(duration_seconds=10, heart_rate_bpm=true_hr)
        result = extractor.extract_heart_rate(ppg_signal)
        
        error = abs(result.heart_rate_bpm - true_hr)
        print(f"  True HR: {true_hr} BPM, Detected: {result.heart_rate_bpm} BPM, " +
              f"Error: {error:.1f} BPM, Confidence: {result.confidence:.0%}")
    
    # Plot example
    print("\n2. Plotting example PPG signal...")
    ppg_signal = simulate_ppg_signal(duration_seconds=15, heart_rate_bpm=72)
    result = extractor.extract_heart_rate(ppg_signal)
    extractor.plot_ppg_with_peaks(ppg_signal, result, title="Simulated PPG Signal")
    
    # Calculate HRV
    if result.peak_times:
        hrv = extractor.calculate_hrv(result.peak_times)
        print("\n3. HRV Metrics:")
        for metric, value in hrv.items():
            if isinstance(value, float):
                print(f"  {metric}: {value:.2f}")
    
    print("\n" + "=" * 60)
    print("To use with real Muse S data:")
    print("1. Enable PPG characteristics in sleep client")
    print("2. Parse 20-bit PPG samples from packets")
    print("3. Use IR channel (850nm) for best results")
    print("4. Apply extract_heart_rate() to continuous signal")
    print("=" * 60)

if __name__ == "__main__":
    main()