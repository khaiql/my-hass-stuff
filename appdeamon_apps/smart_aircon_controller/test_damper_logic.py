#!/usr/bin/env python3
"""
Test script specifically for damper calculation logic
"""

from test_automation_logic import ControllerConfig, ZoneState, HVACMode
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class FixedMockSmartAirconController:
    """Mock controller with corrected damper calculation logic"""
    
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.zones: Dict[str, ZoneState] = {}
        
    def _calculate_damper_positions(self, trigger_zones: List[str], mode: HVACMode) -> Dict[str, int]:
        """Calculate optimal damper positions for all zones - CORRECTED VERSION"""
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
                # Calculate damper position for secondary zones - CORRECTED LOGIC
                if mode == HVACMode.HEAT:
                    # For heating: leverage heat if zone is within reasonable range of target
                    temp_deficit = zone.target_temp - zone.current_temp
                    
                    if temp_deficit > 0:
                        # Zone is below target, could benefit from heating
                        damper_positions[zone_name] = self.config.secondary_damper_percent
                    elif temp_deficit > -self.config.temp_tolerance:
                        # Zone is slightly above target but within tolerance, minimal damper
                        damper_positions[zone_name] = self.config.overflow_damper_percent
                    else:
                        # Zone is well above target, don't heat
                        damper_positions[zone_name] = 0
                        
                else:  # COOL mode
                    # For cooling: leverage cooling if zone is within reasonable range of target
                    temp_excess = zone.current_temp - zone.target_temp
                    
                    if temp_excess > 0:
                        # Zone is above target, could benefit from cooling
                        damper_positions[zone_name] = self.config.secondary_damper_percent
                    elif temp_excess > -self.config.temp_tolerance:
                        # Zone is slightly below target but within tolerance, minimal damper
                        damper_positions[zone_name] = self.config.overflow_damper_percent
                    else:
                        # Zone is well below target, don't cool
                        damper_positions[zone_name] = 0
                        
        return damper_positions


def test_damper_calculation_detailed():
    """Test damper calculation with detailed analysis"""
    print("DETAILED DAMPER CALCULATION TEST")
    print("=" * 50)
    
    config = ControllerConfig(
        smart_hvac_mode="heat", 
        temp_tolerance=0.5,
        primary_damper_percent=50,
        secondary_damper_percent=40,
        overflow_damper_percent=10
    )
    controller = FixedMockSmartAirconController(config)
    
    # Create test scenario based on requirements document
    controller.zones = {
        "baby_bed": ZoneState(
            entity_id="climate.baby_bed_2",
            damper_entity="cover.baby_bed_damper_2", 
            current_temp=19.5,  # At trigger point (20.0 - 0.5)
            target_temp=20.0,
            is_active=True,
            isolation=True
        ),
        "master_bed": ZoneState(
            entity_id="climate.master_bed_", 
            damper_entity="cover.master_bed_damper_2",
            current_temp=19.2,  # Within range (19.0 ± 0.5), could benefit
            target_temp=19.0,
            is_active=True,
            isolation=False
        ),
        "guest_bed": ZoneState(
            entity_id="climate.guest_bed_2",
            damper_entity="cover.guest_bed_damper_2", 
            current_temp=18.6,  # Above max range (18.0 + 0.5 = 18.5)
            target_temp=18.0,
            is_active=True,
            isolation=False
        )
    }
    
    print("SCENARIO FROM REQUIREMENTS DOC:")
    print("- Baby bed: 19.5°C (trigger), target 20.0°C")
    print("- Master bed: 19.2°C (within range), target 19.0°C") 
    print("- Guest bed: 18.6°C (above target), target 18.0°C")
    print()
    
    trigger_zones = ["baby_bed"]
    positions = controller._calculate_damper_positions(trigger_zones, HVACMode.HEAT)
    
    print("CALCULATED DAMPER POSITIONS:")
    for zone_name, position in positions.items():
        zone = controller.zones[zone_name]
        temp_diff = zone.target_temp - zone.current_temp
        print(f"{zone_name:12}: {position:2d}% (temp_diff: {temp_diff:+4.1f}°C)")
        
    print()
    print("EXPECTED FROM REQUIREMENTS:")
    print("- Baby bed: 50% (primary trigger)")
    print("- Master bed: 40-50% (leverage heat)")  
    print("- Guest bed: 5-10% (prevent overheating)")
    
    print()
    print("ANALYSIS:")
    baby_pos = positions["baby_bed"]
    master_pos = positions["master_bed"] 
    guest_pos = positions["guest_bed"]
    
    print(f"✓ Baby bed: {baby_pos}% (Expected: 50% - PRIMARY)")
    
    master_temp_diff = controller.zones["master_bed"].target_temp - controller.zones["master_bed"].current_temp
    print(f"✓ Master bed: {master_pos}% (temp_deficit: {master_temp_diff:+.1f}°C)")
    print(f"  - temp_deficit = target - current = {controller.zones['master_bed'].target_temp} - {controller.zones['master_bed'].current_temp} = {master_temp_diff}")
    print(f"  - temp_deficit > 0? {master_temp_diff} > 0 = {master_temp_diff > 0}")
    print(f"  - temp_deficit > -tolerance? {master_temp_diff} > {-config.temp_tolerance} = {master_temp_diff > -config.temp_tolerance}")
    
    guest_temp_diff = controller.zones["guest_bed"].target_temp - controller.zones["guest_bed"].current_temp  
    print(f"✓ Guest bed: {guest_pos}% (temp_deficit: {guest_temp_diff:+.1f}°C)")
    print(f"  - temp_deficit = target - current = {controller.zones['guest_bed'].target_temp} - {controller.zones['guest_bed'].current_temp} = {guest_temp_diff}")
    print(f"  - temp_deficit > 0? {guest_temp_diff} > 0 = {guest_temp_diff > 0}")
    print(f"  - temp_deficit > -tolerance? {guest_temp_diff} > {-config.temp_tolerance} = {guest_temp_diff > -config.temp_tolerance}")


def test_edge_case_scenarios():
    """Test edge cases in damper calculation"""
    print("\n" + "=" * 50)
    print("EDGE CASE SCENARIOS")
    print("=" * 50)
    
    config = ControllerConfig(smart_hvac_mode="heat", temp_tolerance=0.5)
    controller = FixedMockSmartAirconController(config)
    
    # Test case 1: Isolated zone not in trigger
    print("\nTEST 1: Isolated zone not in trigger list")
    controller.zones = {
        "baby_bed": ZoneState(
            entity_id="climate.baby_bed_2",
            damper_entity="cover.baby_bed_damper_2",
            current_temp=20.2,  # Satisfied
            target_temp=20.0,
            is_active=True,
            isolation=True
        ),
        "living": ZoneState(
            entity_id="climate.living_2", 
            damper_entity="cover.living_damper_2",
            current_temp=19.2,  # Needs heating
            target_temp=20.0,
            is_active=True,
            isolation=False
        )
    }
    
    positions = controller._calculate_damper_positions(["living"], HVACMode.HEAT)
    print(f"Baby bed (isolated, not trigger): {positions['baby_bed']}% - Expected: 0%")
    print(f"Living (trigger): {positions['living']}% - Expected: 50%")
    
    # Test case 2: Zone exactly at boundaries
    print("\nTEST 2: Zones at temperature boundaries")
    controller.zones = {
        "zone_at_lower": ZoneState(
            entity_id="climate.zone1",
            damper_entity="cover.zone1_damper", 
            current_temp=19.5,  # Exactly target - tolerance
            target_temp=20.0,
            is_active=True,
            isolation=False
        ),
        "zone_at_upper": ZoneState(
            entity_id="climate.zone2",
            damper_entity="cover.zone2_damper",
            current_temp=20.5,  # Exactly target + tolerance  
            target_temp=20.0,
            is_active=True,
            isolation=False
        ),
        "trigger_zone": ZoneState(
            entity_id="climate.zone3",
            damper_entity="cover.zone3_damper",
            current_temp=19.4,  # Trigger
            target_temp=20.0, 
            is_active=True,
            isolation=False
        )
    }
    
    positions = controller._calculate_damper_positions(["trigger_zone"], HVACMode.HEAT)
    print(f"Zone at lower boundary (19.5°C): {positions['zone_at_lower']}% - Should get some damper")
    print(f"Zone at upper boundary (20.5°C): {positions['zone_at_upper']}% - Should get minimal/no damper")
    print(f"Trigger zone (19.4°C): {positions['trigger_zone']}% - Expected: 50%")


if __name__ == "__main__":
    test_damper_calculation_detailed()
    test_edge_case_scenarios()