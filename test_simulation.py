#!/usr/bin/env python3
"""Quick test of the Congress simulator."""

import sys
import os
sys.path.insert(0, '/Users/zachpowers/CongressFish')

from backend.simulation.congress_simulator import CongressSimulator
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

if __name__ == '__main__':
    print("🔬 Testing CongressSimulator...")

    try:
        # Initialize
        sim = CongressSimulator()
        print(f"✓ Simulator initialized\n")

        # Test run
        print("📋 Running test simulation...")
        results = sim.run_simulation(
            bill_title="Affordable Health Care Act",
            bill_description="A bill to expand access to healthcare and reduce costs for families.",
            chambers=["House"]  # Just House for quick test
        )

        print("\n✅ Simulation complete!")
        print(f"Status: {results.get('final_status')}")
        print(f"Passed: {results.get('passed')}")
        print(f"Stages: {results.get('total_stages')}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
