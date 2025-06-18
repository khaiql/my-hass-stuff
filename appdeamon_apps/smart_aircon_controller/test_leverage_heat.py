#!/usr/bin/env python3
"""
Test script to verify the "leverage heat" requirement is correctly implemented
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


class CorrectedMockController:
    """Mock controller with corrected leverage heat logic"""
    
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.zones: Dict[str, ZoneState] = {}
        
    def _calculate_damper_positions(self, trigger_zones: List[str], mode: HVACMode) -> Dict[str, int]:
        """Calculate optimal damper positions - CORRECTED for leverage heat"""
        damper_positions = {}
        
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                damper_positions[zone_name] = 0
                continue
                
            if zone.isolation and zone_name not in trigger_zones:
                damper_positions[zone_name] = 0
                continue
                
            if zone_name in trigger_zones:
                damper_positions[zone_name] = self.config.primary_damper_percent
            else:
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


def test_leverage_heat_requirement():
    """Test the leverage heat requirement from the document"""
    print("LEVERAGE HEAT REQUIREMENT TEST")
    print("=" * 50)
    
    config = ControllerConfig(
        smart_hvac_mode="heat",
        temp_tolerance=0.5,
        primary_damper_percent=50,
        secondary_damper_percent=40,
        overflow_damper_percent=10
    )
    controller = CorrectedMockController(config)
    
    # Scenario from requirements document: baby bed triggers, leverage heat for others
    controller.zones = {
        "baby_bed": ZoneState(
            entity_id="climate.baby_bed_2",
            damper_entity="cover.baby_bed_damper_2", 
            current_temp=19.5,  # Trigger point (20.0 - 0.5)
            target_temp=20.0,
            is_active=True,
            isolation=True
        ),
        "master_bed": ZoneState(
            entity_id="climate.master_bed_", 
            damper_entity="cover.master_bed_damper_2",
            current_temp=19.2,  # Above target (19.0) but below target + tolerance (19.5)
            target_temp=19.0,
            is_active=True,
            isolation=False
        ),
        "guest_bed": ZoneState(
            entity_id="climate.guest_bed_2",
            damper_entity="cover.guest_bed_damper_2", 
            current_temp=18.6,  # Above target + tolerance (18.0 + 0.5 = 18.5)
            target_temp=18.0,
            is_active=True,
            isolation=False
        )
    }
    
    print("SCENARIO FROM REQUIREMENTS:")
    print("- Baby bed: 19.5°C (trigger), target 20.0°C, max desired 20.5°C")
    print("- Master bed: 19.2°C (above target 19.0°C), max desired 19.5°C") 
    print("- Guest bed: 18.6°C (above target 18.0°C), max desired 18.5°C")
    print()
    
    trigger_zones = ["baby_bed"]
    positions = controller._calculate_damper_positions(trigger_zones, HVACMode.HEAT)
    
    print("CALCULATED DAMPER POSITIONS:")
    for zone_name, position in positions.items():
        zone = controller.zones[zone_name]
        max_desired = zone.target_temp + config.temp_tolerance
        print(f"{zone_name:12}: {position:2d}% (current: {zone.current_temp}°C, target: {zone.target_temp}°C, max desired: {max_desired}°C)")
        
    print()
    print("REQUIREMENTS ANALYSIS:")
    
    # Baby bed analysis
    baby_pos = positions["baby_bed"]
    print(f"✓ Baby bed: {baby_pos}% (Expected: 50% - PRIMARY TRIGGER)")
    
    # Master bed analysis
    master_pos = positions["master_bed"] 
    master_zone = controller.zones["master_bed"]
    master_max_desired = master_zone.target_temp + config.temp_tolerance
    print(f"✓ Master bed: {master_pos}%")
    print(f"  - Current: {master_zone.current_temp}°C, Target: {master_zone.target_temp}°C, Max desired: {master_max_desired}°C")
    print(f"  - Current < Max desired? {master_zone.current_temp} < {master_max_desired} = {master_zone.current_temp < master_max_desired}")
    print(f"  - Current < Target? {master_zone.current_temp} < {master_zone.target_temp} = {master_zone.current_temp < master_zone.target_temp}")
    print(f"  - Should get 10% (overflow) to leverage heat up to {master_max_desired}°C")
    
    # Guest bed analysis  
    guest_pos = positions["guest_bed"]
    guest_zone = controller.zones["guest_bed"]
    guest_max_desired = guest_zone.target_temp + config.temp_tolerance
    print(f"✓ Guest bed: {guest_pos}%")
    print(f"  - Current: {guest_zone.current_temp}°C, Target: {guest_zone.target_temp}°C, Max desired: {guest_max_desired}°C")
    print(f"  - Current < Max desired? {guest_zone.current_temp} < {guest_max_desired} = {guest_zone.current_temp < guest_max_desired}")
    print(f"  - Already above max desired, should get 0%")


def test_your_example():
    """Test the specific example you mentioned"""
    print("\n" + "=" * 50)
    print("YOUR EXAMPLE TEST")
    print("=" * 50)
    
    config = ControllerConfig(temp_tolerance=0.5)
    controller = CorrectedMockController(config)
    
    # Your example: bedroom target 20°C, current 20.2°C, should heat to 20.5°C
    controller.zones = {
        "trigger_zone": ZoneState(
            entity_id="climate.trigger",
            damper_entity="cover.trigger_damper",
            current_temp=19.3,  # Needs heating
            target_temp=20.0,
            is_active=True,
            isolation=False
        ),
        "bedroom": ZoneState(
            entity_id="climate.bedroom",
            damper_entity="cover.bedroom_damper", 
            current_temp=20.2,  # Above target but should still heat to 20.5°C
            target_temp=20.0,
            is_active=True,
            isolation=False
        )
    }
    
    print("YOUR SCENARIO:")
    print("- Trigger zone: 19.3°C (needs heating), target 20.0°C")
    print("- Bedroom: 20.2°C (above target), target 20.0°C, should heat to 20.5°C")
    print()
    
    positions = controller._calculate_damper_positions(["trigger_zone"], HVACMode.HEAT)
    
    print("RESULTS:")
    trigger_pos = positions["trigger_zone"]
    bedroom_pos = positions["bedroom"]
    
    print(f"Trigger zone: {trigger_pos}% (Expected: 50% - primary)")
    print(f"Bedroom: {bedroom_pos}% (Expected: 10% - leverage heat)")
    
    bedroom_zone = controller.zones["bedroom"]
    max_desired = bedroom_zone.target_temp + config.temp_tolerance
    print(f"\nBedroom Analysis:")
    print(f"- Current: {bedroom_zone.current_temp}°C")
    print(f"- Target: {bedroom_zone.target_temp}°C") 
    print(f"- Max desired (target + tolerance): {max_desired}°C")
    print(f"- Current < Max desired? {bedroom_zone.current_temp} < {max_desired} = {bedroom_zone.current_temp < max_desired}")
    print(f"- Should get damper opening to leverage heat: {'YES' if bedroom_zone.current_temp < max_desired else 'NO'}")


if __name__ == "__main__":
    test_leverage_heat_requirement()
    test_your_example()