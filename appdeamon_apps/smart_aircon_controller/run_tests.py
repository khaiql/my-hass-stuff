#!/usr/bin/env python3
"""
Test runner for Smart Aircon Controller

This script runs the simplified tests that work with mocked AppDaemon dependencies.
"""

import sys
import os
import subprocess

def run_simple_tests():
    """Run the simplified tests"""
    print("Running Smart Aircon Controller Tests (Simple)...")
    print("=" * 60)
    
    try:
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "."], 
                              capture_output=True, text=True,
                              cwd=os.path.dirname(os.path.abspath(__file__)))
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        return result.returncode == 0
    except Exception as e:
        print(f"Error running tests: {e}")
        return False

def run_coverage_tests():
    """Run tests with coverage"""
    print("Running Smart Aircon Controller Tests with Coverage...")
    print("=" * 60)
    
    try:
        # Run with coverage
        result = subprocess.run([
            sys.executable, "-m", "coverage", "run", "--source=.", "-m", "unittest", "discover", "."
        ], capture_output=True, text=True,
           cwd=os.path.dirname(os.path.abspath(__file__)))
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            # Generate coverage report
            subprocess.run([sys.executable, "-m", "coverage", "report"],
                           cwd=os.path.dirname(os.path.abspath(__file__)))
            subprocess.run([sys.executable, "-m", "coverage", "html"],
                           cwd=os.path.dirname(os.path.abspath(__file__)))
            print("\nHTML coverage report generated in: htmlcov/")
        
        return result.returncode == 0
    except Exception as e:
        print(f"Error running coverage tests: {e}")
        return False

def main():
    """Main test runner"""
    if len(sys.argv) > 1 and sys.argv[1] == "--coverage":
        success = run_coverage_tests()
    else:
        success = run_simple_tests()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 