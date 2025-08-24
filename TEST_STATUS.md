# Test Status

## Current Test Results
- **47 tests passing** ✅ 
- **0 tests failing** 🎉

## Passing Test Categories
✅ Raw binary stream operations (8/8 tests)
✅ Real-time decoder functionality (7/7 tests) 
✅ PPG heart rate extraction (6/6 tests)
✅ fNIRS processor functions (6/6 tests)
✅ Integration tests (11/11 tests)
✅ Package structure and imports (9/9 tests)

## Test Data
- Tests now use **real captured data** from Muse S device
- 5 seconds of real packets stored in `tests/test_data/`
- Automatic fallback to synthetic data if real data unavailable

## Running Tests

### Quick tests (fast, core functionality):
```bash
python run_tests.py
```

### All tests:
```bash
python -m pytest tests/
```

### Specific test file:
```bash
python -m pytest tests/test_raw_stream.py -v
```

## Test Performance
- Core tests run in < 2 seconds
- Full test suite runs in < 5 seconds
- All tests properly handle edge cases and invalid input