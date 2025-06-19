#!/usr/bin/env python3
"""
Test runner for Smart Aircon Controller

This script runs tests using pytest.
"""

import sys
import os
import subprocess

def run_pytest(coverage=False):
    """Helper to run pytest with or without coverage."""
    print(f"Running Smart Aircon Controller Tests with pytest {'(Coverage)' if coverage else ''}...")
    print("=" * 60)
    
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Go one level up to the 'apps' directory to fix import paths
    project_root = os.path.dirname(script_dir)

    try:
        cmd = [sys.executable, "-m", "pytest"]
        if coverage:
            cmd.extend(["--cov=smart_aircon_controller", "--cov-report=term-missing", "--cov-report=html"])
        
        # Specify the test directory
        cmd.append("smart_aircon_controller/")

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
            
        if coverage and result.returncode == 0:
            print(f"\nHTML coverage report generated in: {os.path.join(script_dir, 'htmlcov')}")

        return result.returncode == 0
    except Exception as e:
        print(f"Error running tests: {e}")
        return False

def main():
    """Main test runner"""
    use_coverage = len(sys.argv) > 1 and sys.argv[1] == "--coverage"
    success = run_pytest(coverage=use_coverage)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 