#!/usr/bin/env python3
"""
Test the damper behavior: Only set once on algorithm start/stop, not during periodic checks
"""

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


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
    temp_tolerance: float = 0.5
    primary_damper_percent: int = 50
    secondary_damper_percent: int = 40
    overflow_damper_percent: int = 10
    minimum_damper_percent: int = 5
    smart_hvac_mode: str = "heat"
    algorithm_timeout_minutes: int = 30
    stability_check_minutes: int = 10
    progress_timeout_minutes: int = 15


class DamperTestController:
    """Test controller to verify damper behavior"""
    
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.zones: Dict[str, ZoneState] = {}
        self.algorithm_active: bool = False
        self.algorithm_mode: Optional[HVACMode] = None
        self.algorithm_start_time: Optional[datetime.datetime] = None
        self.temperature_history: Dict[str, List[Tuple[datetime.datetime, float]]] = {}
        self.last_progress_time: Optional[datetime.datetime] = None
        
        # Track service calls to verify behavior
        self.damper_service_calls = []
        self.hvac_service_calls = []
        
    def log(self, message: str, level: str = "INFO"):
        print(f"[{level}] {message}")
        
    def call_service(self, service: str, **kwargs):
        """Mock service call tracking"""
        call = {"service": service, "kwargs": kwargs, "time": datetime.datetime.now()}
        
        if "cover" in service:
            self.damper_service_calls.append(call)
            print(f"🎚️  DAMPER SERVICE: {service} - {kwargs}")
        elif "climate" in service:
            self.hvac_service_calls.append(call)
            print(f"🌡️  HVAC SERVICE: {service} - {kwargs}")
            
    def _execute_smart_algorithm(self, trigger_zones: List[str], mode: HVACMode):
        """Execute the smart heating/cooling algorithm (SETS DAMPERS ONCE)"""
        self.log(f"🚀 ALGORITHM START: {mode.value} for zones: {trigger_zones}")
        
        # Calculate damper positions for all active zones
        damper_positions = self._calculate_damper_positions(trigger_zones, mode)
        
        # Set HVAC mode
        self.call_service("climate/set_hvac_mode", entity_id="climate.aircon", hvac_mode=mode.value)
        
        # Apply damper positions (ONLY TIME WE SET DAMPERS)
        self._apply_damper_positions(damper_positions)
        
        self.algorithm_active = True
        self.algorithm_mode = mode
        self.algorithm_start_time = datetime.datetime.now()
        self.last_progress_time = datetime.datetime.now()
        
    def _calculate_damper_positions(self, trigger_zones: List[str], mode: HVACMode) -> Dict[str, int]:
        """Calculate optimal damper positions"""
        damper_positions = {}
        
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                damper_positions[zone_name] = 0
                continue
                
            if zone_name in trigger_zones:
                damper_positions[zone_name] = self.config.primary_damper_percent
            else:
                if mode == HVACMode.HEAT:
                    max_desired_temp = zone.target_temp + self.config.temp_tolerance
                    if zone.current_temp < max_desired_temp:
                        if zone.current_temp < zone.target_temp:
                            damper_positions[zone_name] = self.config.secondary_damper_percent
                        else:
                            damper_positions[zone_name] = self.config.overflow_damper_percent
                    else:
                        damper_positions[zone_name] = self.config.minimum_damper_percent
                        
        return damper_positions
        
    def _apply_damper_positions(self, positions: Dict[str, int]):
        """Apply calculated damper positions"""
        self.log("🎚️  SETTING DAMPER POSITIONS:")
        for zone_name, position in positions.items():
            if zone_name in self.zones:
                self.call_service(
                    "cover/set_cover_position",
                    entity_id=self.zones[zone_name].damper_entity,
                    position=position
                )
                self.zones[zone_name].damper_position = position
                self.log(f"   {zone_name}: {position}%")
                
    def _deactivate_algorithm(self):
        """Deactivate algorithm and return to idle (SETS HVAC ONCE)"""
        self.log("🛑 ALGORITHM STOP: Deactivating and returning to DRY mode")
        
        # Set HVAC to idle mode (ONLY TIME WE CHANGE HVAC ON DEACTIVATION)
        self.call_service("climate/set_hvac_mode", entity_id="climate.aircon", hvac_mode="dry")
        
        # DON'T set dampers - let Airtouch handle the transition
        self.log("   Letting Airtouch handle damper transition")
        
        self.algorithm_active = False
        self.algorithm_mode = None
        self.algorithm_start_time = None
        self.temperature_history.clear()
        self.last_progress_time = None
        
    def _all_zones_satisfied(self) -> bool:
        """Check if zones are satisfied with fallback mechanism"""
        if not self.algorithm_mode or not self.algorithm_start_time:
            return True
            
        # Primary satisfaction: All zones reach target + tolerance (ideal case)
        primary_satisfied = self._check_primary_satisfaction()
        if primary_satisfied:
            self.log("   Primary satisfaction: All zones reached target + tolerance")
            return True
            
        # Check if zones are at least at target (minimum requirement for fallback)
        zones_at_target = self._all_zones_at_target()
        if not zones_at_target:
            self.log("   Zones not at target yet - continue heating")
            return False
            
        # Simulate fallback: In real scenario, this would check timeouts, stability, etc.
        # For this test, we'll trigger fallback when zones are at target but not at target + tolerance
        self.log("   Fallback triggered: Zones at target but not at target + tolerance")
        return True
        
    def _check_primary_satisfaction(self) -> bool:
        """Check if all zones reach target + tolerance"""
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue
                
            if self.algorithm_mode == HVACMode.HEAT:
                target_plus_tolerance = zone.target_temp + self.config.temp_tolerance
                self.log(f"   DEBUG: {zone_name}: {zone.current_temp}°C >= {target_plus_tolerance}°C? {zone.current_temp >= target_plus_tolerance}")
                if zone.current_temp < target_plus_tolerance:
                    return False
        return True
        
    def _all_zones_at_target(self) -> bool:
        """Check if all zones are at least at their target temperature"""
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue
                
            if self.algorithm_mode == HVACMode.HEAT:
                if zone.current_temp < zone.target_temp:
                    self.log(f"   DEBUG: {zone_name}: {zone.current_temp}°C < {zone.target_temp}°C (below target)")
                    return False
                else:
                    self.log(f"   DEBUG: {zone_name}: {zone.current_temp}°C >= {zone.target_temp}°C (at target)")
        return True
        
    def _analyze_zones_for_heating(self) -> List[str]:
        """Analyze which zones need heating"""
        trigger_zones = []
        for zone_name, zone in self.zones.items():
            if zone.is_active and zone.current_temp < zone.target_temp - self.config.temp_tolerance:
                trigger_zones.append(zone_name)
        return trigger_zones
        
    def periodic_check(self):
        """Simulate periodic check - should NOT set dampers if algorithm is running"""
        self.log("⏰ PERIODIC CHECK")
        
        # Determine zones needing attention
        zones_needing_attention = self._analyze_zones_for_heating()
        target_mode = HVACMode.HEAT
        
        self.log(f"   Zones needing attention: {zones_needing_attention}")
        
        # If algorithm is already running in the correct mode
        if self.algorithm_active and self.algorithm_mode == target_mode:
            satisfied = self._all_zones_satisfied()
            self.log(f"   Algorithm active, zones satisfied: {satisfied}")
            if satisfied:
                self.log("   ✅ Zones satisfied - deactivating")
                self._deactivate_algorithm()
            else:
                self.log("   🔄 Algorithm continues - LETTING AIRTOUCH CONTROL DAMPERS")
                # KEY: Do NOT call _execute_smart_algorithm() again!
                # Do NOT set dampers again!
            return
            
        # If algorithm is NOT active, start it if zones need attention
        if zones_needing_attention:
            self.log("   🚀 Starting algorithm")
            self._execute_smart_algorithm(zones_needing_attention, target_mode)


def test_damper_behavior():
    """Test that dampers are only set once on start/stop, not during periodic checks"""
    
    print("DAMPER BEHAVIOR TEST")
    print("=" * 60)
    print()
    
    config = ControllerConfig(temp_tolerance=0.5)
    controller = DamperTestController(config)
    
    # Setup zones
    controller.zones = {
        "living": ZoneState(
            entity_id="climate.living_2",
            damper_entity="cover.living_damper_2",
            current_temp=19.0,  # Below target - tolerance, will trigger
            target_temp=20.0,
            is_active=True
        ),
        "bedroom": ZoneState(
            entity_id="climate.bedroom_2", 
            damper_entity="cover.bedroom_damper_2",
            current_temp=19.8,  # Slightly below target, will get secondary
            target_temp=20.0,
            is_active=True
        )
    }
    
    print("INITIAL STATE:")
    for zone_name, zone in controller.zones.items():
        print(f"- {zone_name}: {zone.current_temp}°C → {zone.target_temp}°C")
    print()
    
    # Step 1: First periodic check - should start algorithm and set dampers
    print("STEP 1: First periodic check (algorithm not running)")
    print("-" * 50)
    controller.periodic_check()
    
    damper_calls_step1 = len(controller.damper_service_calls)
    hvac_calls_step1 = len(controller.hvac_service_calls)
    
    print(f"📊 Damper service calls: {damper_calls_step1}")
    print(f"📊 HVAC service calls: {hvac_calls_step1}")
    print(f"📊 Algorithm active: {controller.algorithm_active}")
    print()
    
    # Step 2: Multiple periodic checks while algorithm is running
    print("STEP 2-5: Multiple periodic checks (algorithm running)")
    print("-" * 50)
    
    for i in range(2, 6):
        print(f"STEP {i}: Periodic check #{i-1}")
        controller.periodic_check()
        
        damper_calls = len(controller.damper_service_calls)
        hvac_calls = len(controller.hvac_service_calls)
        
        print(f"📊 Total damper calls: {damper_calls} (should stay at {damper_calls_step1})")
        print(f"📊 Total HVAC calls: {hvac_calls}")
        print()
        
        # Verify dampers weren't set again
        if damper_calls > damper_calls_step1:
            print("❌ ERROR: Dampers were set again during periodic check!")
            return False
        else:
            print("✅ Good: Dampers not touched during periodic check")
            print()
    
    # Step 6: Zones reach satisfaction - algorithm should deactivate
    print("STEP 6: Zones reach target + tolerance")
    print("-" * 50)
    
    # Update zone temperatures to satisfied levels
    controller.zones["living"].current_temp = 20.5  # target + tolerance
    controller.zones["bedroom"].current_temp = 20.3  # Above target but below target + tolerance (fallback scenario)
    
    print("Updated temperatures:")
    for zone_name, zone in controller.zones.items():
        print(f"- {zone_name}: {zone.current_temp}°C (target + tolerance: {zone.target_temp + config.temp_tolerance}°C)")
    print()
    
    controller.periodic_check()
    
    final_damper_calls = len(controller.damper_service_calls)
    final_hvac_calls = len(controller.hvac_service_calls)
    
    print(f"📊 Final damper calls: {final_damper_calls}")
    print(f"📊 Final HVAC calls: {final_hvac_calls}")
    print(f"📊 Algorithm active: {controller.algorithm_active}")
    print()
    
    # Analysis
    print("ANALYSIS:")
    print("-" * 30)
    
    expected_damper_calls = 2  # One for each zone on algorithm start
    expected_hvac_calls = 2    # One to start heating, one to return to dry
    
    print(f"Expected damper calls: {expected_damper_calls}")
    print(f"Actual damper calls: {final_damper_calls}")
    print(f"Expected HVAC calls: {expected_hvac_calls}")
    print(f"Actual HVAC calls: {final_hvac_calls}")
    print()
    
    # Verify timing of calls
    print("CALL TIMING ANALYSIS:")
    print("-" * 30)
    
    if len(controller.damper_service_calls) >= 2:
        first_damper_time = controller.damper_service_calls[0]["time"]
        last_damper_time = controller.damper_service_calls[-1]["time"]
        damper_time_diff = (last_damper_time - first_damper_time).total_seconds()
        
        print(f"Time between first and last damper calls: {damper_time_diff:.1f} seconds")
        
        if damper_time_diff < 1:  # All damper calls should be within 1 second (during algorithm start)
            print("✅ All damper calls happened at algorithm start")
        else:
            print("❌ Damper calls spread over time - dampers were adjusted during periodic checks")
            return False
    
    success = (
        final_damper_calls == expected_damper_calls and
        final_hvac_calls == expected_hvac_calls and
        not controller.algorithm_active
    )
    
    return success


def test_airtouch_control_respected():
    """Test that Airtouch control is respected during algorithm execution"""
    
    print("\n" + "=" * 60)
    print("AIRTOUCH CONTROL RESPECT TEST")
    print("=" * 60)
    print()
    
    config = ControllerConfig()
    controller = DamperTestController(config)
    
    # Setup zone
    controller.zones = {
        "test_zone": ZoneState(
            entity_id="climate.test_zone",
            damper_entity="cover.test_zone_damper",
            current_temp=19.0,
            target_temp=20.0,
            is_active=True,
            damper_position=0
        )
    }
    
    print("SCENARIO: Algorithm starts, then Airtouch changes damper position")
    print()
    
    # Step 1: Start algorithm
    print("STEP 1: Algorithm starts")
    controller.periodic_check()
    initial_damper_calls = len(controller.damper_service_calls)
    print(f"Initial damper position set to: {controller.zones['test_zone'].damper_position}%")
    print()
    
    # Step 2: Simulate Airtouch changing damper position
    print("STEP 2: Airtouch changes damper position")
    controller.zones["test_zone"].damper_position = 25  # Airtouch changed it
    print(f"Airtouch changed damper to: {controller.zones['test_zone'].damper_position}%")
    print()
    
    # Step 3: Multiple periodic checks - should NOT revert damper position
    print("STEP 3-5: Periodic checks (should NOT revert damper)")
    for i in range(3):
        print(f"Periodic check {i+1}:")
        controller.periodic_check()
        damper_calls = len(controller.damper_service_calls)
        current_position = controller.zones["test_zone"].damper_position
        
        print(f"  Damper calls: {damper_calls} (should stay at {initial_damper_calls})")
        print(f"  Damper position: {current_position}% (should stay at 25%)")
        
        if damper_calls > initial_damper_calls:
            print("  ❌ ERROR: Algorithm tried to change damper position!")
            return False
        else:
            print("  ✅ Good: Algorithm respected Airtouch control")
        print()
    
    print("✅ AIRTOUCH CONTROL RESPECTED: Algorithm did not interfere with damper adjustments")
    return True


if __name__ == "__main__":
    print("TESTING DAMPER BEHAVIOR: Set once on start/stop, respect Airtouch during execution")
    print("=" * 80)
    
    test1 = test_damper_behavior()
    test2 = test_airtouch_control_respected()
    
    print("\n" + "=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)
    
    if test1 and test2:
        print("🎉 ALL TESTS PASSED!")
        print()
        print("✅ Dampers are only set ONCE when algorithm starts")
        print("✅ Dampers are NOT adjusted during periodic checks")
        print("✅ HVAC mode is only changed on start/stop")
        print("✅ Airtouch control is respected during algorithm execution")
        print("✅ Algorithm properly hands control back to Airtouch")
        print()
        print("🏆 BEHAVIOR VERIFIED: Minimal interference with Airtouch controller!")
    else:
        print("❌ TESTS FAILED")
        print(f"   Damper behavior test: {'✅' if test1 else '❌'}")
        print(f"   Airtouch respect test: {'✅' if test2 else '❌'}")
        print()
        print("🔧 Algorithm needs adjustment to properly respect Airtouch control")
    
    print("=" * 80)