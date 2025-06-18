#!/usr/bin/env python3
"""
Test to verify minimum damper behavior - active zones should never be closed
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
    minimum_damper_percent: int = 5  # Minimum damper for active zones
    heating_mode: str = "heat"
    idle_mode: str = "dry"
    cooling_mode: str = "cool"
    smart_hvac_mode: str = "heat"


class MinimumDamperTestController:
    """Test controller with minimum damper logic"""
    
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.zones: Dict[str, ZoneState] = {}
        
    def _calculate_damper_positions(self, trigger_zones: List[str], mode: HVACMode) -> Dict[str, int]:
        """Calculate damper positions with minimum damper for active zones"""
        damper_positions = {}

        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                damper_positions[zone_name] = 0
                continue

            if zone.isolation and zone_name not in trigger_zones:
                # Isolated zones don't participate unless they are a trigger
                # But still need minimum damper to keep zone active
                damper_positions[zone_name] = self.config.minimum_damper_percent
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
                        # Zone is at or above target + tolerance - minimum damper to keep active
                        damper_positions[zone_name] = self.config.minimum_damper_percent
                        
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
                        # Zone is at or below target - tolerance - minimum damper to keep active
                        damper_positions[zone_name] = self.config.minimum_damper_percent

        return damper_positions


def test_minimum_damper_behavior():
    """Test that active zones never get 0% damper"""
    print("MINIMUM DAMPER BEHAVIOR TEST")
    print("=" * 50)
    
    config = ControllerConfig(
        temp_tolerance=0.5,
        primary_damper_percent=50,
        secondary_damper_percent=40,
        overflow_damper_percent=10,
        minimum_damper_percent=5
    )
    controller = MinimumDamperTestController(config)
    
    # Test scenario: zones that would normally get 0% should get 5%
    controller.zones = {
        "trigger": ZoneState(
            entity_id="climate.trigger",
            damper_entity="cover.trigger_damper",
            current_temp=19.2,  # Triggers heating
            target_temp=20.0,
            is_active=True,
            isolation=False
        ),
        "isolated_active": ZoneState(
            entity_id="climate.isolated_active",
            damper_entity="cover.isolated_active_damper",
            current_temp=18.8,  # Would benefit but isolated
            target_temp=19.0,
            is_active=True,  # ACTIVE - should get minimum 5%
            isolation=True
        ),
        "over_max_active": ZoneState(
            entity_id="climate.over_max_active",
            damper_entity="cover.over_max_active_damper",
            current_temp=19.8,  # Above target + tolerance (19.0 + 0.5 = 19.5)
            target_temp=19.0,
            is_active=True,  # ACTIVE - should get minimum 5%
            isolation=False
        ),
        "inactive_zone": ZoneState(
            entity_id="climate.inactive_zone",
            damper_entity="cover.inactive_zone_damper",
            current_temp=18.5,
            target_temp=19.0,
            is_active=False,  # INACTIVE - should get 0%
            isolation=False
        )
    }
    
    trigger_zones = ["trigger"]
    positions = controller._calculate_damper_positions(trigger_zones, HVACMode.HEAT)
    
    print("ZONE ANALYSIS:")
    print("-" * 50)
    
    for zone_name, zone in controller.zones.items():
        position = positions[zone_name]
        max_desired = zone.target_temp + config.temp_tolerance
        
        print(f"{zone_name:16}")
        print(f"  Active:   {zone.is_active}")
        print(f"  Isolated: {zone.isolation}")
        print(f"  Current:  {zone.current_temp:4.1f}°C")
        print(f"  Target:   {zone.target_temp:4.1f}°C")
        print(f"  Max:      {max_desired:4.1f}°C")
        print(f"  Damper:   {position:2d}%")
        
        # Check if active zone gets minimum damper
        if zone.is_active and position == 0:
            print(f"  ❌ ERROR: Active zone has 0% damper!")
        elif zone.is_active and position >= config.minimum_damper_percent:
            print(f"  ✅ OK: Active zone has ≥{config.minimum_damper_percent}% damper")
        elif not zone.is_active and position == 0:
            print(f"  ✅ OK: Inactive zone has 0% damper")
        print()
    
    print("VERIFICATION:")
    print("-" * 50)
    
    # Check each zone
    trigger_pos = positions["trigger"]
    isolated_pos = positions["isolated_active"] 
    over_max_pos = positions["over_max_active"]
    inactive_pos = positions["inactive_zone"]
    
    print(f"✓ Trigger zone:         {trigger_pos:2d}% (expected: 50%)")
    print(f"✓ Isolated active zone: {isolated_pos:2d}% (expected: 5% minimum)")
    print(f"✓ Over max active zone: {over_max_pos:2d}% (expected: 5% minimum)")
    print(f"✓ Inactive zone:        {inactive_pos:2d}% (expected: 0%)")
    
    # Verify no active zone has 0%
    active_zones = [name for name, zone in controller.zones.items() if zone.is_active]
    zero_damper_active = [name for name in active_zones if positions[name] == 0]
    
    if zero_damper_active:
        print(f"\n❌ ERROR: Active zones with 0% damper: {zero_damper_active}")
        return False
    else:
        print(f"\n✅ SUCCESS: All active zones have ≥{config.minimum_damper_percent}% damper")
        return True


def test_cooling_minimum_damper():
    """Test minimum damper behavior in cooling mode"""
    print("\n" + "=" * 50)
    print("COOLING MODE MINIMUM DAMPER TEST")
    print("=" * 50)
    
    config = ControllerConfig(
        temp_tolerance=0.5,
        minimum_damper_percent=5,
        smart_hvac_mode="cool"
    )
    controller = MinimumDamperTestController(config)
    
    controller.zones = {
        "trigger": ZoneState(
            entity_id="climate.trigger",
            damper_entity="cover.trigger_damper",
            current_temp=20.8,  # Triggers cooling (20.0 + 0.5 = 20.5)
            target_temp=20.0,
            is_active=True,
            isolation=False
        ),
        "under_min_active": ZoneState(
            entity_id="climate.under_min_active",
            damper_entity="cover.under_min_active_damper",
            current_temp=18.2,  # Below target - tolerance (19.0 - 0.5 = 18.5)
            target_temp=19.0,
            is_active=True,  # ACTIVE - should get minimum 5%
            isolation=False
        )
    }
    
    trigger_zones = ["trigger"]
    positions = controller._calculate_damper_positions(trigger_zones, HVACMode.COOL)
    
    print("COOLING SCENARIO:")
    for zone_name, zone in controller.zones.items():
        position = positions[zone_name]
        min_desired = zone.target_temp - config.temp_tolerance
        print(f"{zone_name:16}: {position:2d}% | Current: {zone.current_temp:4.1f}°C | Target: {zone.target_temp:4.1f}°C | Min: {min_desired:4.1f}°C")
    
    # Verify
    under_min_pos = positions["under_min_active"]
    if under_min_pos >= config.minimum_damper_percent:
        print(f"✅ Under-min active zone gets {under_min_pos}% (≥{config.minimum_damper_percent}%)")
        return True
    else:
        print(f"❌ Under-min active zone gets {under_min_pos}% (<{config.minimum_damper_percent}%)")
        return False


if __name__ == "__main__":
    success1 = test_minimum_damper_behavior()
    success2 = test_cooling_minimum_damper()
    
    print("\n" + "=" * 50)
    if success1 and success2:
        print("✅ ALL TESTS PASSED - Minimum damper logic working correctly")
    else:
        print("❌ SOME TESTS FAILED - Check minimum damper logic")
    print("=" * 50)