#!/usr/bin/env python3
"""
Quick test runner to verify repair service implementation.
"""
import subprocess
import sys

def main():
    """Run the repair service tests."""
    print("=" * 80)
    print("🧪 Running Repair Service Tests")
    print("=" * 80)
    print()
    
    # Run pytest with verbose output
    result = subprocess.run(
        [sys.executable, "-m", "pytest", 
         "tests/test_repair_service.py", 
         "-v",
         "--tb=short",
         "-s"],  # Show print statements
        cwd="backend"
    )
    
    print()
    print("=" * 80)
    if result.returncode == 0:
        print("✅ All repair tests passed!")
    else:
        print("❌ Some tests failed. Check output above.")
    print("=" * 80)
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(main())
