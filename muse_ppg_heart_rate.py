"""
Muse S PPG and Heart Rate Extraction
Processes PPG (Photoplethysmography) data to extract heart rate.

Based on Muse S Athena specifications:
- Optics: 8 channels at 64 Hz (preset p1034)
- EEG: 20-bit LSB-first packed samples
- Wavelengths: ~850nm NIR, ~735nm IR
"""

import numpy as np
from scipy import signal
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
from typing import List, Optional
from dataclasses import dataclass

import muse_athena_protocol as proto

@dataclass
class PPGData:
    """Container for PPG samples"""
    timestamp: float
    channels: dict          # channel_name -> list of values
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

    def parse_ppg_packet(self, data: bytes, n_channels: int = 8) -> Optional[PPGData]:
        """
        Parse optics/PPG data using 20-bit LSB-first unpacking.

        Args:
            data: Raw optics data bytes (not including TAG/header).
            n_channels: Number of optics channels (4, 8, or 16).

        Returns:
            PPGData with decoded channel values, or None on failure.
        """
        config = {4: 30, 8: 40, 16: 40}
        expected_len = config.get(n_channels)
        if expected_len is None or len(data) < expected_len:
            return None

        try:
            arr = proto.decode_optics(data, n_channels)
            # arr shape: (n_samples, n_channels)

            if n_channels == 8:
                names = proto.OPTICS_CHANNELS_8
            else:
                names = [f"opt{i}" for i in range(n_channels)]

            channels = {}
            for ch_idx in range(n_channels):
                ch_name = names[ch_idx] if ch_idx < len(names) else f"opt{ch_idx}"
                channels[ch_name] = arr[:, ch_idx].tolist()

            return PPGData(
                timestamp=0.0,
                channels=channels,
            )

        except Exception:
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
        ppg_detrended = signal.detrend(ppg_signal)

        # Step 2: Bandpass filter (0.5-4 Hz for heart rate 30-240 BPM)
        nyquist = sample_rate / 2
        low_cut = 0.5 / nyquist
        high_cut = 4.0 / nyquist

        b, a = signal.butter(4, [low_cut, high_cut], btype='band')
        ppg_filtered = signal.filtfilt(b, a, ppg_detrended)

        # Step 3: Find peaks (heartbeats)
        ppg_normalized = (ppg_filtered - np.mean(ppg_filtered)) / np.std(ppg_filtered)

        min_distance = int(0.4 * sample_rate)  # Minimum 150 BPM

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

        plt.subplot(2, 1, 1)
        plt.plot(time_axis, ppg_signal, 'b-', linewidth=0.5, alpha=0.7)
        plt.ylabel('PPG Amplitude')
        plt.title(f'{title} - HR: {result.heart_rate_bpm} BPM')
        plt.grid(True, alpha=0.3)

        if result.peak_times:
            peak_indices = [int(t * sample_rate) for t in result.peak_times if t * sample_rate < len(ppg_signal)]
            plt.plot(np.array(peak_indices) / sample_rate,
                    ppg_signal[peak_indices], 'ro', markersize=8)

        plt.subplot(2, 1, 2)
        ppg_detrended = signal.detrend(ppg_signal)
        nyquist = sample_rate / 2
        b, a = signal.butter(4, [0.5/nyquist, 4.0/nyquist], btype='band')
        ppg_filtered = signal.filtfilt(b, a, ppg_detrended)

        plt.plot(time_axis, ppg_filtered, 'g-', linewidth=0.8)
        plt.xlabel('Time (seconds)')
        plt.ylabel('Filtered PPG')
        plt.grid(True, alpha=0.3)

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

        rr_intervals = np.diff(peak_times) * 1000

        hrv_metrics = {
            "mean_rr_ms": np.mean(rr_intervals),
            "sdnn_ms": np.std(rr_intervals),
            "rmssd_ms": np.sqrt(np.mean(np.diff(rr_intervals)**2)),
            "pnn50": np.sum(np.abs(np.diff(rr_intervals)) > 50) / len(rr_intervals) * 100
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

    heart_freq = heart_rate_bpm / 60

    pulse = np.sin(2 * np.pi * heart_freq * t)
    dicrotic = 0.3 * np.sin(4 * np.pi * heart_freq * t - np.pi/4)
    respiratory = 0.1 * np.sin(2 * np.pi * 0.25 * t)
    noise = 0.05 * np.random.randn(len(t))

    ppg = pulse + dicrotic + respiratory + noise
    ppg = 1000 + 100 * ppg

    return ppg

def main():
    """Test heart rate extraction"""

    print("=" * 60)
    print("PPG Heart Rate Extraction Test")
    print("=" * 60)

    extractor = PPGHeartRateExtractor()

    print("\n1. Testing with simulated PPG signal...")

    test_rates = [60, 75, 90, 120]

    for true_hr in test_rates:
        ppg_signal = simulate_ppg_signal(duration_seconds=10, heart_rate_bpm=true_hr)
        result = extractor.extract_heart_rate(ppg_signal)

        error = abs(result.heart_rate_bpm - true_hr)
        print(f"  True HR: {true_hr} BPM, Detected: {result.heart_rate_bpm} BPM, " +
              f"Error: {error:.1f} BPM, Confidence: {result.confidence:.0%}")

    print("\n2. Plotting example PPG signal...")
    ppg_signal = simulate_ppg_signal(duration_seconds=15, heart_rate_bpm=72)
    result = extractor.extract_heart_rate(ppg_signal)
    extractor.plot_ppg_with_peaks(ppg_signal, result, title="Simulated PPG Signal")

    if result.peak_times:
        hrv = extractor.calculate_hrv(result.peak_times)
        print("\n3. HRV Metrics:")
        for metric, value in hrv.items():
            if isinstance(value, float):
                print(f"  {metric}: {value:.2f}")

    print("\n" + "=" * 60)
    print("To use with real Muse S data:")
    print("1. Decode optics packets with proto.decode_optics()")
    print("2. Use LO_NIR channel (~850nm) for best HR results")
    print("3. Apply extract_heart_rate() to continuous signal")
    print("=" * 60)

if __name__ == "__main__":
    main()
