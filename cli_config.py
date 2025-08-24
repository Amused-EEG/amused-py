#!/usr/bin/env python
"""
Amused Configuration CLI
Command-line tool for managing Muse device connections and settings
"""

import asyncio
import argparse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from amused import MuseDeviceConfig


async def scan_command(args):
    """Handle scan command"""
    config = MuseDeviceConfig()
    devices = await config.scan_for_devices(timeout=args.timeout)
    
    if not devices:
        print("No Muse devices found")
        return 1
    
    print(f"\nFound {len(devices)} device(s):")
    for i, dev in enumerate(devices, 1):
        signal = "Strong" if dev.rssi > -60 else "Medium" if dev.rssi > -75 else "Weak"
        preferred = " [PREFERRED]" if dev.preferred else ""
        print(f"{i}. {dev.name} - {dev.model}")
        print(f"   Address: {dev.address}")
        print(f"   Signal: {signal} ({dev.rssi} dBm){preferred}")
    
    return 0


async def list_command(args):
    """Handle list command"""
    config = MuseDeviceConfig()
    devices = config.list_devices()
    
    if not devices:
        print("No known devices. Run 'amused-config scan' first.")
        return 1
    
    print("\nKnown Muse devices:")
    for dev in devices:
        preferred = " [PREFERRED]" if dev.preferred else ""
        print(f"- {dev.name} ({dev.model}){preferred}")
        print(f"  Address: {dev.address}")
        print(f"  Last seen: {dev.last_seen}")
    
    return 0


async def prefer_command(args):
    """Handle prefer command"""
    config = MuseDeviceConfig()
    
    if args.address:
        # Set by address
        if config.set_preferred_device(args.address):
            print(f"Set {args.address} as preferred device")
            return 0
        else:
            print(f"Device {args.address} not found")
            return 1
    
    # Interactive selection
    devices = config.list_devices()
    if not devices:
        print("No known devices. Run 'amused-config scan' first.")
        return 1
    
    print("\nSelect device to set as preferred:")
    for i, dev in enumerate(devices, 1):
        print(f"{i}. {dev.name} - {dev.address}")
    
    try:
        choice = int(input("\nDevice number (0 to cancel): "))
        if choice == 0:
            return 0
        if 1 <= choice <= len(devices):
            device = devices[choice - 1]
            config.set_preferred_device(device.address)
            print(f"\nSet {device.name} as preferred device")
            return 0
    except (ValueError, IndexError):
        pass
    
    print("Invalid selection")
    return 1


async def buffer_command(args):
    """Handle buffer configuration"""
    config = MuseDeviceConfig()
    
    if args.list:
        print("\nCurrent buffer sizes:")
        print(f"  EEG window: {config.get_buffer_size('eeg_window')} samples (256 Hz)")
        print(f"  PPG window: {config.get_buffer_size('ppg_window')} samples (64 Hz)")
        print(f"  IMU window: {config.get_buffer_size('imu_window')} samples (52 Hz)")
        print(f"  Heart rate: {config.get_buffer_size('heart_rate_window')} points")
        
        print("\nTime windows:")
        print(f"  EEG: {config.get_buffer_size('eeg_window') / 256:.1f} seconds")
        print(f"  PPG: {config.get_buffer_size('ppg_window') / 64:.1f} seconds")
        print(f"  IMU: {config.get_buffer_size('imu_window') / 52:.1f} seconds")
        return 0
    
    if args.type and args.size:
        buffer_types = {
            'eeg': 'eeg_window',
            'ppg': 'ppg_window', 
            'imu': 'imu_window',
            'hr': 'heart_rate_window'
        }
        
        if args.type not in buffer_types:
            print(f"Invalid buffer type. Choose from: {', '.join(buffer_types.keys())}")
            return 1
        
        if config.set_buffer_size(buffer_types[args.type], args.size):
            print(f"Set {args.type} buffer to {args.size} samples")
            
            # Show time equivalent
            if args.type == 'eeg':
                print(f"  = {args.size / 256:.1f} seconds at 256 Hz")
            elif args.type == 'ppg':
                print(f"  = {args.size / 64:.1f} seconds at 64 Hz")
            elif args.type == 'imu':
                print(f"  = {args.size / 52:.1f} seconds at 52 Hz")
            
            return 0
        else:
            return 1
    
    print("Use --list to see current settings or --type and --size to change")
    return 1


async def test_command(args):
    """Test connection to a device"""
    config = MuseDeviceConfig()
    
    print("Testing Muse connection...")
    result = await config.quick_connect()
    
    if result:
        device, client = result
        print(f"\n✓ Successfully connected to {device.name}")
        print(f"  Model: {device.model}")
        print(f"  Address: {device.address}")
        
        # Test complete, disconnect
        await client.disconnect()
        print("✓ Connection test successful")
        return 0
    else:
        print("\n✗ Connection test failed")
        print("  Check that your Muse is powered on and in range")
        return 1


async def remove_command(args):
    """Remove a device from configuration"""
    config = MuseDeviceConfig()
    
    if args.address:
        if config.remove_device(args.address):
            print(f"Removed device {args.address}")
            return 0
        else:
            print(f"Device {args.address} not found")
            return 1
    
    # Interactive removal
    devices = config.list_devices()
    if not devices:
        print("No devices to remove")
        return 0
    
    print("\nSelect device to remove:")
    for i, dev in enumerate(devices, 1):
        print(f"{i}. {dev.name} - {dev.address}")
    
    try:
        choice = int(input("\nDevice number (0 to cancel): "))
        if choice == 0:
            return 0
        if 1 <= choice <= len(devices):
            device = devices[choice - 1]
            config.remove_device(device.address)
            print(f"\nRemoved {device.name}")
            return 0
    except (ValueError, IndexError):
        pass
    
    print("Invalid selection")
    return 1


async def interactive_command(args):
    """Run interactive configuration"""
    from muse_config import interactive_setup
    await interactive_setup()
    return 0


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Amused Device Configuration Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  amused-config scan              # Scan for nearby Muse devices
  amused-config list              # List known devices
  amused-config prefer            # Set preferred device
  amused-config test              # Test connection
  amused-config buffer --list     # Show buffer settings
  amused-config interactive       # Interactive setup
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan for Muse devices')
    scan_parser.add_argument('-t', '--timeout', type=float, default=5.0,
                            help='Scan timeout in seconds (default: 5)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List known devices')
    
    # Prefer command
    prefer_parser = subparsers.add_parser('prefer', help='Set preferred device')
    prefer_parser.add_argument('address', nargs='?', help='Device MAC address')
    
    # Buffer command
    buffer_parser = subparsers.add_parser('buffer', help='Configure buffer sizes')
    buffer_parser.add_argument('--list', action='store_true', help='List current settings')
    buffer_parser.add_argument('--type', choices=['eeg', 'ppg', 'imu', 'hr'],
                              help='Buffer type to configure')
    buffer_parser.add_argument('--size', type=int, help='Buffer size in samples')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test device connection')
    
    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove device')
    remove_parser.add_argument('address', nargs='?', help='Device MAC address')
    
    # Interactive command
    interactive_parser = subparsers.add_parser('interactive', help='Interactive setup')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Command dispatch
    commands = {
        'scan': scan_command,
        'list': list_command,
        'prefer': prefer_command,
        'buffer': buffer_command,
        'test': test_command,
        'remove': remove_command,
        'interactive': interactive_command,
    }
    
    try:
        result = asyncio.run(commands[args.command](args))
        return result
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        return 1
    except Exception as e:
        print(f"\nError: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())