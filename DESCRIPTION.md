# Amused - Project Description

## GitHub Repository Description (Short)
**🧠 First open-source BLE protocol for Muse S EEG headsets. Stream brain waves, heart rate, and blood oxygen without proprietary SDKs. Pure Python implementation.**

## GitHub Repository Description (Full)

### Amused: A Muse S Direct Protocol Implementation

Finally, the breakthrough the neuroscience and BCI community has been waiting for! Amused is the **first publicly available** reverse-engineered implementation of the Muse S Bluetooth Low Energy protocol. 

After countless forum posts and GitHub issues requesting this capability, we've cracked the code that InteraXon's proprietary SDK has kept locked away. The key discovery? The `dc001` streaming command must be sent TWICE - a critical detail that stumped everyone who tried before.

### What Makes This Special

🎯 **First of Its Kind**: Nobody else has published a working Muse S protocol implementation  
🔓 **Truly Open**: MIT licensed, no proprietary dependencies  
🧪 **Research Ready**: Direct access to raw sensor data for your experiments  
💡 **Community Driven**: Built by researchers, for researchers  

### Complete Sensor Access

- **EEG Brain Waves**: 4-5 channels at 256 Hz native sampling
- **PPG Heart Rate**: 3-wavelength photoplethysmography (IR, NIR, Red)  
- **fNIRS Blood Oxygenation**: Real-time cerebral hemodynamics (HbO2, HbR, TSI)
- **IMU Motion**: 9-axis accelerometer and gyroscope
- **Sleep Monitoring**: 8+ hour continuous recording sessions

### Perfect For

- **Neuroscience Research**: Direct access to EEG without SDK limitations
- **BCI Development**: Build brain-computer interfaces with full control
- **Sleep Studies**: Complete biometric monitoring through the night
- **Meditation Apps**: Real-time brain state feedback
- **Biohacking**: Track your cognitive performance and optimization
- **Education**: Learn BLE protocols and biosignal processing

### Why "Amused"?

It's a playful acronym for "**A Muse S Direct**" connection - and yes, we're quite amused that we finally solved what nobody else could! This represents months of packet sniffing, protocol analysis, and careful reverse engineering.

### Technical Highlights

- Pure Python with Bleak BLE library
- No compilation or native dependencies
- Cross-platform (Windows, Linux, macOS)
- Async/await modern architecture
- CSV data export for analysis
- Real-time processing pipelines

### Get Started in 30 Seconds

```python
pip install amused

import amused
client = amused.MuseSleepClient()  # Full sensors
await client.connect_and_monitor()  # Start streaming!
```

### Community Impact

For years, researchers and developers have been forced to use InteraXon's closed SDK, limiting what they could build and research. With Amused, you have complete freedom to:
- Modify the protocol
- Access raw unfiltered data
- Build commercial applications
- Integrate with any platform
- Contribute improvements

This is more than just code - it's freedom for the Muse community.

### Keywords/Topics

`muse` `eeg` `neuroscience` `brain-computer-interface` `bci` `ble` `bluetooth` `ppg` `heart-rate` `hrv` `fnirs` `blood-oxygen` `meditation` `sleep-monitoring` `biometrics` `neurofeedback` `brainwaves` `cognitive-science` `quantified-self` `biohacking` `open-source` `reverse-engineering`

### Star This Repository If...

⭐ You've been waiting for open Muse S access  
⭐ You believe in open-source neuroscience  
⭐ You want to support further development  
⭐ This saves you from the proprietary SDK  

---

**Join us in democratizing brain-computer interfaces!**