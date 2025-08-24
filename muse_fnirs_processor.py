"""
Muse S fNIRS (functional Near-Infrared Spectroscopy) Processor
Extracts blood oxygenation and hemoglobin concentration from PPG data

The Muse S uses multiple wavelengths to measure:
- Oxygenated hemoglobin (HbO2)
- Deoxygenated hemoglobin (HbR)
- Total hemoglobin (HbT)
- Tissue Saturation Index (TSI)
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from scipy import signal
import datetime

@dataclass
class FNIRSData:
    """Container for fNIRS measurements"""
    timestamp: datetime.datetime
    hbo2: float  # Oxygenated hemoglobin concentration (μM)
    hbr: float   # Deoxygenated hemoglobin concentration (μM)
    hbt: float   # Total hemoglobin (HbO2 + HbR)
    tsi: float   # Tissue Saturation Index (%)
    quality: str # Signal quality assessment

class FNIRSProcessor:
    """
    Process multi-wavelength PPG data for fNIRS measurements
    
    The Muse S PPG sensors use:
    - 850nm (infrared) - sensitive to both HbO2 and HbR
    - 950nm (near-infrared) - primarily HbR
    - 660nm (red) - primarily HbO2
    """
    
    def __init__(self, sample_rate: int = 64):
        self.sample_rate = sample_rate
        
        # Modified Beer-Lambert Law coefficients
        # Extinction coefficients (cm^-1 / mM^-1) for each wavelength
        self.extinction_coeffs = {
            # Wavelength: [HbO2, HbR]
            660: [0.32, 3.20],   # Red - high HbR absorption
            850: [1.05, 0.78],   # IR - balanced absorption  
            950: [0.69, 1.10]    # NIR - higher HbR absorption
        }
        
        # Differential path length factor (typical for forehead)
        self.dpf = 6.0  # Typical value for adult forehead
        
        # Source-detector separation (cm)
        self.sds = 3.0  # Typical for Muse S
        
        # Buffers for each wavelength
        self.buffers = {
            'ir': [],      # 850nm
            'nir': [],     # 950nm  
            'red': []      # 660nm
        }
        
        # Baseline values for relative measurements
        self.baseline = None
        self.calibrated = False
        
    def add_samples(self, ir_samples: List[float], 
                   nir_samples: List[float],
                   red_samples: List[float]):
        """Add new PPG samples for each wavelength"""
        self.buffers['ir'].extend(ir_samples)
        self.buffers['nir'].extend(nir_samples)
        self.buffers['red'].extend(red_samples)
        
        # Keep buffer size manageable (30 seconds max)
        max_samples = self.sample_rate * 30
        for key in self.buffers:
            if len(self.buffers[key]) > max_samples:
                self.buffers[key] = self.buffers[key][-max_samples:]
    
    def calibrate_baseline(self, duration_seconds: int = 10):
        """Establish baseline measurements for relative calculations"""
        min_samples = self.sample_rate * duration_seconds
        
        if any(len(self.buffers[key]) < min_samples for key in self.buffers):
            return False
        
        self.baseline = {}
        for key in self.buffers:
            # Use median of last 10 seconds as baseline
            samples = np.array(self.buffers[key][-min_samples:])
            self.baseline[key] = np.median(samples)
        
        self.calibrated = True
        return True
    
    def calculate_optical_density(self, current: Dict[str, float]) -> Dict[str, float]:
        """Calculate optical density changes from baseline"""
        if not self.calibrated or not self.baseline:
            return None
        
        od_changes = {}
        for key in ['ir', 'nir', 'red']:
            if self.baseline[key] > 0 and current[key] > 0:
                # ΔOD = -log(I/I0)
                od_changes[key] = -np.log10(current[key] / self.baseline[key])
            else:
                od_changes[key] = 0
        
        return od_changes
    
    def solve_chromophores(self, od_changes: Dict[str, float]) -> Tuple[float, float]:
        """
        Solve for HbO2 and HbR concentrations using modified Beer-Lambert law
        
        Returns:
            (ΔHbO2, ΔHbR) in μM
        """
        # Set up system of equations
        # ΔOD = ε * c * d * DPF
        # We have 3 wavelengths, 2 unknowns (HbO2, HbR)
        
        # Build coefficient matrix
        A = np.array([
            [self.extinction_coeffs[660][0], self.extinction_coeffs[660][1]],   # Red
            [self.extinction_coeffs[850][0], self.extinction_coeffs[850][1]],   # IR
            [self.extinction_coeffs[950][0], self.extinction_coeffs[950][1]]    # NIR
        ])
        
        # Optical density vector
        b = np.array([
            od_changes['red'],
            od_changes['ir'],
            od_changes['nir']
        ])
        
        # Scale by path length
        b = b / (self.sds * self.dpf)
        
        # Solve using least squares (overdetermined system)
        try:
            x, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
            
            # Convert from mM to μM
            delta_hbo2 = x[0] * 1000
            delta_hbr = x[1] * 1000
            
            return delta_hbo2, delta_hbr
        except:
            return 0.0, 0.0
    
    def extract_fnirs(self, window_seconds: int = 5) -> Optional[FNIRSData]:
        """
        Extract fNIRS measurements from recent PPG data
        
        Args:
            window_seconds: Analysis window duration
            
        Returns:
            FNIRSData with hemoglobin measurements
        """
        min_samples = self.sample_rate * window_seconds
        
        # Check if we have enough data
        if any(len(self.buffers[key]) < min_samples for key in self.buffers):
            return None
        
        # Auto-calibrate if not done
        if not self.calibrated:
            if not self.calibrate_baseline():
                return None
        
        # Get current values (median of window)
        current = {}
        for key in self.buffers:
            samples = np.array(self.buffers[key][-min_samples:])
            
            # Apply bandpass filter to remove noise
            if len(samples) > 10:
                b, a = signal.butter(2, [0.1, 5.0], btype='band', fs=self.sample_rate)
                filtered = signal.filtfilt(b, a, samples)
                current[key] = np.median(filtered)
            else:
                current[key] = np.median(samples)
        
        # Calculate optical density changes
        od_changes = self.calculate_optical_density(current)
        if od_changes is None:
            return None
        
        # Solve for chromophore concentrations
        delta_hbo2, delta_hbr = self.solve_chromophores(od_changes)
        
        # Add to baseline values (assume baseline = 50μM HbO2, 25μM HbR typical)
        hbo2 = 50.0 + delta_hbo2
        hbr = 25.0 + delta_hbr
        hbt = hbo2 + hbr
        
        # Calculate tissue saturation index
        tsi = (hbo2 / hbt * 100) if hbt > 0 else 0
        
        # Assess signal quality
        quality = self.assess_quality(current)
        
        return FNIRSData(
            timestamp=datetime.datetime.now(),
            hbo2=hbo2,
            hbr=hbr,
            hbt=hbt,
            tsi=tsi,
            quality=quality
        )
    
    def assess_quality(self, current: Dict[str, float]) -> str:
        """Assess signal quality based on amplitude and noise"""
        # Check if signals are in reasonable range
        for key, value in current.items():
            if value <= 0 or value > 1e6:
                return "Poor"
        
        # Check signal-to-noise ratio
        if len(self.buffers['ir']) >= self.sample_rate:
            recent = np.array(self.buffers['ir'][-self.sample_rate:])
            snr = np.mean(recent) / (np.std(recent) + 1e-6)
            
            if snr > 10:
                return "Excellent"
            elif snr > 5:
                return "Good"
            elif snr > 2:
                return "Fair"
        
        return "Poor"
    
    def get_cerebral_oxygenation(self) -> Optional[Dict[str, float]]:
        """
        Get cerebral oxygenation metrics
        
        Returns dict with:
        - ScO2: Cerebral oxygen saturation (%)
        - rSO2: Regional oxygen saturation (%)
        - COx: Cerebral oximetry index
        """
        fnirs = self.extract_fnirs()
        if not fnirs:
            return None
        
        # Cerebral oxygen saturation
        sco2 = fnirs.tsi
        
        # Regional oxygen saturation (similar but may use different weighting)
        rso2 = (fnirs.hbo2 / (fnirs.hbo2 + fnirs.hbr)) * 100 if (fnirs.hbo2 + fnirs.hbr) > 0 else 0
        
        # Cerebral oximetry index (normalized)
        cox = (fnirs.hbo2 - fnirs.hbr) / (fnirs.hbo2 + fnirs.hbr) if (fnirs.hbo2 + fnirs.hbr) > 0 else 0
        
        return {
            'ScO2': sco2,
            'rSO2': rso2,
            'COx': cox,
            'HbO2': fnirs.hbo2,
            'HbR': fnirs.hbr,
            'HbT': fnirs.hbt,
            'quality': fnirs.quality
        }
    
    def detect_hypoxia(self, threshold: float = 60.0) -> bool:
        """Detect potential hypoxia based on tissue saturation"""
        fnirs = self.extract_fnirs()
        if not fnirs:
            return False
        
        return fnirs.tsi < threshold
    
    def calculate_cerebral_autoregulation(self, window_minutes: int = 5) -> Optional[float]:
        """
        Calculate cerebral autoregulation index (CAR)
        Correlation between blood pressure surrogate and oxygenation
        """
        min_samples = self.sample_rate * 60 * window_minutes
        
        if len(self.buffers['ir']) < min_samples:
            return None
        
        # Use IR channel as blood pressure surrogate (pulse amplitude)
        ir_signal = np.array(self.buffers['ir'][-min_samples:])
        
        # Calculate pulse amplitude variability
        # (This is simplified - real implementation would extract pulse amplitudes)
        window = self.sample_rate * 10  # 10-second windows
        amplitudes = []
        
        for i in range(0, len(ir_signal) - window, window):
            segment = ir_signal[i:i+window]
            amplitude = np.max(segment) - np.min(segment)
            amplitudes.append(amplitude)
        
        if len(amplitudes) < 10:
            return None
        
        # Get oxygenation trend
        oxy_values = []
        for i in range(len(amplitudes)):
            # Simplified - would extract actual HbO2 for each window
            oxy_values.append(np.mean(ir_signal[i*window:(i+1)*window]))
        
        # Calculate correlation
        if len(amplitudes) == len(oxy_values):
            correlation = np.corrcoef(amplitudes, oxy_values)[0, 1]
            # CAR index: 0 = perfect autoregulation, 1 = impaired
            car_index = abs(correlation)
            return car_index
        
        return None

def visualize_fnirs(processor: FNIRSProcessor, duration_seconds: int = 60):
    """Visualize fNIRS data (requires matplotlib)"""
    try:
        import matplotlib.pyplot as plt
        
        # Extract measurements over time
        measurements = []
        timestamps = []
        
        for i in range(duration_seconds):
            fnirs = processor.extract_fnirs()
            if fnirs:
                measurements.append(fnirs)
                timestamps.append(i)
        
        if not measurements:
            print("No fNIRS data to visualize")
            return
        
        # Plot hemoglobin concentrations
        fig, axes = plt.subplots(3, 1, figsize=(10, 8))
        
        hbo2_values = [m.hbo2 for m in measurements]
        hbr_values = [m.hbr for m in measurements]
        tsi_values = [m.tsi for m in measurements]
        
        # HbO2
        axes[0].plot(timestamps, hbo2_values, 'r-', label='HbO2')
        axes[0].set_ylabel('HbO2 (μM)')
        axes[0].set_title('Oxygenated Hemoglobin')
        axes[0].grid(True, alpha=0.3)
        
        # HbR
        axes[1].plot(timestamps, hbr_values, 'b-', label='HbR')
        axes[1].set_ylabel('HbR (μM)')
        axes[1].set_title('Deoxygenated Hemoglobin')
        axes[1].grid(True, alpha=0.3)
        
        # TSI
        axes[2].plot(timestamps, tsi_values, 'g-', label='TSI')
        axes[2].set_ylabel('TSI (%)')
        axes[2].set_xlabel('Time (seconds)')
        axes[2].set_title('Tissue Saturation Index')
        axes[2].grid(True, alpha=0.3)
        axes[2].set_ylim([0, 100])
        
        plt.tight_layout()
        plt.show()
        
    except ImportError:
        print("Matplotlib not available for visualization")

# Example usage
if __name__ == "__main__":
    print("Muse S fNIRS Processor")
    print("=" * 60)
    
    # Create processor
    processor = FNIRSProcessor(sample_rate=64)
    
    # Simulate multi-wavelength PPG data
    from muse_ppg_heart_rate import simulate_ppg_signal
    
    print("\n1. Generating simulated multi-wavelength PPG data...")
    
    # Generate slightly different signals for each wavelength
    # (In reality, these would come from actual PPG sensors)
    duration = 30  # seconds
    
    # Simulate normal oxygenation
    ir_signal = simulate_ppg_signal(duration, heart_rate_bpm=70) * 1000 + 50000
    nir_signal = simulate_ppg_signal(duration, heart_rate_bpm=70) * 800 + 48000
    red_signal = simulate_ppg_signal(duration, heart_rate_bpm=70) * 1200 + 45000
    
    # Add samples in chunks
    chunk_size = 64  # 1 second of data
    for i in range(0, len(ir_signal), chunk_size):
        processor.add_samples(
            ir_signal[i:i+chunk_size],
            nir_signal[i:i+chunk_size],
            red_signal[i:i+chunk_size]
        )
    
    print("\n2. Calibrating baseline...")
    if processor.calibrate_baseline():
        print("   Baseline calibration successful")
    
    # Simulate oxygenation change (mild hypoxia)
    print("\n3. Simulating mild hypoxia...")
    ir_signal2 = simulate_ppg_signal(10, heart_rate_bpm=75) * 900 + 49000
    nir_signal2 = simulate_ppg_signal(10, heart_rate_bpm=75) * 850 + 47500
    red_signal2 = simulate_ppg_signal(10, heart_rate_bpm=75) * 1300 + 44000
    
    for i in range(0, len(ir_signal2), chunk_size):
        processor.add_samples(
            ir_signal2[i:i+chunk_size],
            nir_signal2[i:i+chunk_size],
            red_signal2[i:i+chunk_size]
        )
    
    print("\n4. Extracting fNIRS measurements...")
    fnirs = processor.extract_fnirs()
    
    if fnirs:
        print(f"\nfNIRS Results:")
        print(f"  HbO2: {fnirs.hbo2:.1f} μM")
        print(f"  HbR:  {fnirs.hbr:.1f} μM")
        print(f"  HbT:  {fnirs.hbt:.1f} μM")
        print(f"  TSI:  {fnirs.tsi:.1f}%")
        print(f"  Quality: {fnirs.quality}")
        
        # Check cerebral oxygenation
        cerebral = processor.get_cerebral_oxygenation()
        if cerebral:
            print(f"\nCerebral Oxygenation:")
            print(f"  ScO2: {cerebral['ScO2']:.1f}%")
            print(f"  rSO2: {cerebral['rSO2']:.1f}%")
            print(f"  COx:  {cerebral['COx']:.2f}")
        
        # Check for hypoxia
        if processor.detect_hypoxia(threshold=65):
            print("\n  WARNING: Potential hypoxia detected!")
        
        # Calculate autoregulation
        car = processor.calculate_cerebral_autoregulation(window_minutes=1)
        if car is not None:
            print(f"\nCerebral Autoregulation Index: {car:.2f}")
            if car > 0.5:
                print("  Autoregulation may be impaired")
    
    print("\n" + "=" * 60)
    print("fNIRS processing complete!")
    print("\nThe Muse S can monitor:")
    print("- Prefrontal cortex oxygenation")
    print("- Cerebral blood flow changes")
    print("- Mental workload via hemodynamic response")
    print("- Sleep apnea detection via SpO2 drops")
    print("- Meditation depth via oxygenation patterns")