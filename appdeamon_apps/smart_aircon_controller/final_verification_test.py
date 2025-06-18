#!/usr/bin/env python3
"""
Final verification test using the exact logic from smart_aircon_controller.py
"""

import sys
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class HVACMode(Enum):
    HEAT = "heat"
    COOL = "cool"
    DRY = "dry"
    OFF = "off"


@dataclass
class ZoneState:
    entity_id: str
    damper_entity: str
    current_temp: float
    target_temp: float
    is_active: bool
    isolation: bool = False
    damper_position: int = 0


@dataclass
class ControllerConfig:
    enabled: bool = True
    check_interval: int = 30
    temp_tolerance: float = 0.5
    main_climate: str = "climate.aircon"
    primary_damper_percent: int = 50
    secondary_damper_percent: int = 40
    overflow_damper_percent: int = 10
    heating_mode: str = "heat"
    idle_mode: str = "dry"
    cooling_mode: str = "cool"
    smart_hvac_mode: str = "heat"


class FinalTestController:
    """Final test controller with exact logic from smart_aircon_controller.py"""
    
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.zones: Dict[str, ZoneState] = {}
        
    def _calculate_damper_positions(self, trigger_zones: List[str], mode: HVACMode) -> Dict[str, int]:
        """EXACT COPY of the corrected logic from smart_aircon_controller.py"""
        damper_positions = {}
        
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                damper_positions[zone_name] = 0
                continue
                
            if zone.isolation and zone_name not in trigger_zones:
                # Isolated zones don't participate unless they are a trigger
                damper_positions[zone_name] = 0
                continue
                
            if zone_name in trigger_zones:
                # Primary trigger zone gets full damper opening
                damper_positions[zone_name] = self.config.primary_damper_percent
            else:
                # Calculate damper position for secondary zones
                if mode == HVACMode.HEAT:
                    # For heating: leverage heat to bring zones up to target + tolerance
                    max_desired_temp = zone.target_temp + self.config.temp_tolerance
                    
                    if zone.current_temp < max_desired_temp:
                        # Zone can benefit from heating (below target + tolerance)
                        if zone.current_temp < zone.target_temp:
                            # Zone is below target - give it secondary damper percentage
                            damper_positions[zone_name] = self.config.secondary_damper_percent
                        else:
                            # Zone is above target but below target + tolerance - minimal damper
                            damper_positions[zone_name] = self.config.overflow_damper_percent
                    else:
                        # Zone is at or above target + tolerance - don't heat further
                        damper_positions[zone_name] = 0
                        
                else:  # COOL mode
                    # For cooling: leverage cooling to bring zones down to target - tolerance
                    min_desired_temp = zone.target_temp - self.config.temp_tolerance
                    
                    if zone.current_temp > min_desired_temp:
                        # Zone can benefit from cooling (above target - tolerance)
                        if zone.current_temp > zone.target_temp:
                            # Zone is above target - give it secondary damper percentage
                            damper_positions[zone_name] = self.config.secondary_damper_percent
                        else:
                            # Zone is below target but above target - tolerance - minimal damper
                            damper_positions[zone_name] = self.config.overflow_damper_percent
                    else:
                        # Zone is at or below target - tolerance - don't cool further
                        damper_positions[zone_name] = 0
                        
        return damper_positions


def final_verification():
    """Final verification of the leverage heat logic"""
    print("FINAL VERIFICATION - LEVERAGE HEAT LOGIC")
    print("=" * 60)
    
    config = ControllerConfig(
        temp_tolerance=0.5,
        primary_damper_percent=50,
        secondary_damper_percent=40,
        overflow_damper_percent=10
    )
    controller = FinalTestController(config)
    
    # Test scenario demonstrating all cases
    controller.zones = {
        "trigger": ZoneState(
            entity_id="climate.trigger",
            damper_entity="cover.trigger_damper",
            current_temp=19.2,  # Below target - tolerance (19.5), triggers
            target_temp=20.0,
            is_active=True,
            isolation=False
        ),
        "below_target": ZoneState(
            entity_id="climate.below_target",
            damper_entity="cover.below_target_damper",
            current_temp=18.8,  # Below target (19.0) - should get 40%
            target_temp=19.0,
            is_active=True,
            isolation=False
        ),
        "above_target_leverage": ZoneState(
            entity_id="climate.above_target_leverage",
            damper_entity="cover.above_target_leverage_damper",
            current_temp=20.2,  # Above target (20.0) but below max (20.5) - should get 10%
            target_temp=20.0,
            is_active=True,
            isolation=False
        ),
        "at_max": ZoneState(
            entity_id="climate.at_max",
            damper_entity="cover.at_max_damper",
            current_temp=19.5,  # At target + tolerance - should get 0%
            target_temp=19.0,
            is_active=True,
            isolation=False
        ),
        "isolated": ZoneState(
            entity_id="climate.isolated",
            damper_entity="cover.isolated_damper",
            current_temp=18.8,  # Would benefit but is isolated - should get 0%
            target_temp=19.0,
            is_active=True,
            isolation=True
        )
    }
    
    trigger_zones = ["trigger"]
    positions = controller._calculate_damper_positions(trigger_zones, HVACMode.HEAT)
    
    print("ZONE ANALYSIS:")
    print("-" * 60)
    
    for zone_name, zone in controller.zones.items():
        max_desired = zone.target_temp + config.temp_tolerance
        position = positions[zone_name]
        
        print(f"{zone_name:20}")
        print(f"  Current: {zone.current_temp:4.1f}°C")
        print(f"  Target:  {zone.target_temp:4.1f}°C")
        print(f"  Max:     {max_desired:4.1f}°C")
        print(f"  Damper:  {position:2d}%")
        
        # Explain the logic
        if zone_name in trigger_zones:
            print(f"  Logic:   PRIMARY TRIGGER → {config.primary_damper_percent}%")
        elif zone.isolation:
            print(f"  Logic:   ISOLATED (not trigger) → 0%")
        elif zone.current_temp < max_desired:
            if zone.current_temp < zone.target_temp:
                print(f"  Logic:   BELOW TARGET → {config.secondary_damper_percent}%")
            else:
                print(f"  Logic:   ABOVE TARGET, LEVERAGE HEAT → {config.overflow_damper_percent}%")
        else:
            print(f"  Logic:   AT/ABOVE MAX → 0%")
        print()
    
    print("EXPECTED RESULTS:")
    print("✓ trigger:                50% (primary trigger)")
    print("✓ below_target:           40% (below target, normal heating)")
    print("✓ above_target_leverage:  10% (leverage heat up to max)")
    print("✓ at_max:                  0% (already at maximum)")
    print("✓ isolated:                0% (isolated, not trigger)")
    
    print("\nVERIFICATION:")
    expected = {
        "trigger": 50,
        "below_target": 40,
        "above_target_leverage": 10,
        "at_max": 0,
        "isolated": 0
    }
    
    all_correct = True
    for zone_name, expected_pos in expected.items():
        actual_pos = positions[zone_name]
        status = "✓" if actual_pos == expected_pos else "✗"
        print(f"{status} {zone_name:20}: {actual_pos:2d}% (expected {expected_pos:2d}%)")
        if actual_pos != expected_pos:
            all_correct = False
    
    print(f"\nFINAL RESULT: {'✓ ALL CORRECT' if all_correct else '✗ ERRORS FOUND'}")


if __name__ == "__main__":
    final_verification()