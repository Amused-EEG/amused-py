#!/usr/bin/env python
"""
Test runner for Amused library
Runs fast tests by default, use --all for complete test suite
"""

import sys
import unittest
import argparse

def run_fast_tests():
    """Run only fast tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add fast test modules
    fast_modules = [
        'tests.test_raw_stream',
        'tests.test_realtime_decoder',
        'tests.test_ppg_fnirs_fast',  # Fast version
    ]
    
    for module in fast_modules:
        try:
            suite.addTests(loader.loadTestsFromName(module))
        except:
            print(f"Warning: Could not load {module}")
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

def run_all_tests():
    """Run complete test suite"""
    loader = unittest.TestLoader()
    suite = loader.discover('tests')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

def main():
    parser = argparse.ArgumentParser(description='Run Amused tests')
    parser.add_argument('--all', action='store_true', 
                       help='Run all tests including slow ones')
    parser.add_argument('--integration', action='store_true',
                       help='Run integration tests')
    args = parser.parse_args()
    
    print("="*60)
    print("Amused Test Suite")
    print("="*60)
    
    if args.all:
        print("Running ALL tests (may take a while)...")
        success = run_all_tests()
    elif args.integration:
        print("Running integration tests...")
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName('tests.test_integration')
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        success = result.wasSuccessful()
    else:
        print("Running fast tests only (use --all for complete suite)...")
        success = run_fast_tests()
    
    print("\n" + "="*60)
    if success:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
        sys.exit(1)

if __name__ == '__main__':
    main()