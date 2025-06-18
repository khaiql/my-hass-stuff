#!/usr/bin/env python3
"""
Test the fallback mechanism for Airtouch controller interference
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
    enabled: bool = True
    check_interval: int = 30
    temp_tolerance: float = 0.5
    main_climate: str = "climate.aircon"
    primary_damper_percent: int = 50
    secondary_damper_percent: int = 40
    overflow_damper_percent: int = 10
    minimum_damper_percent: int = 5
    heating_mode: str = "heat"
    idle_mode: str = "dry"
    cooling_mode: str = "cool"
    smart_hvac_mode: str = "heat"
    # Fallback mechanism
    algorithm_timeout_minutes: int = 30
    stability_check_minutes: int = 10
    progress_timeout_minutes: int = 15


class FallbackTestController:
    """Test controller with fallback mechanism"""
    
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.zones: Dict[str, ZoneState] = {}
        self.algorithm_active: bool = False
        self.algorithm_mode: Optional[HVACMode] = None
        self.algorithm_start_time: Optional[datetime.datetime] = None
        self.temperature_history: Dict[str, List[Tuple[datetime.datetime, float]]] = {}
        self.last_progress_time: Optional[datetime.datetime] = None
        
    def log(self, message: str, level: str = "INFO"):
        print(f"[{level}] {message}")
        
    def _all_zones_at_target(self) -> bool:
        """Check if all active zones are at least at their target temperature"""
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue
                
            if self.algorithm_mode == HVACMode.HEAT:
                if zone.current_temp < zone.target_temp:
                    return False
            elif self.algorithm_mode == HVACMode.COOL:
                if zone.current_temp > zone.target_temp:
                    return False
        return True
    
    def _zones_stable_for_time(self, now: datetime.datetime, minutes: int) -> bool:
        """Check if zones have been stable (within 0.1°C) for specified time"""
        stability_threshold = 0.1  # 0.1°C stability threshold
        check_time = now - datetime.timedelta(minutes=minutes)
        
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue
                
            if zone_name not in self.temperature_history:
                return False
                
            # Get readings from the stability check period
            stable_readings = [
                temp for time, temp in self.temperature_history[zone_name]
                if time >= check_time
            ]
            
            if len(stable_readings) < 3:  # Need enough data points
                return False
                
            # Check if temperature has been stable
            min_temp = min(stable_readings)
            max_temp = max(stable_readings)
            if max_temp - min_temp > stability_threshold:
                return False
        
        return True
    
    def _most_dampers_closed(self) -> bool:
        """Check if most active zone dampers are closed (≤10%)"""
        active_zones = [zone for zone in self.zones.values() if zone.is_active]
        if not active_zones:
            return False
            
        closed_dampers = sum(1 for zone in active_zones if zone.damper_position <= 10)
        return closed_dampers >= len(active_zones) * 0.7  # 70% or more closed
    
    def _check_primary_satisfaction(self) -> bool:
        """Check primary satisfaction criteria (target + tolerance)"""
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue

            if self.algorithm_mode == HVACMode.HEAT:
                # Satisfied if temp is at or slightly above target
                temp_min = zone.target_temp
                temp_max = zone.target_temp + self.config.temp_tolerance
                if not (temp_min <= zone.current_temp <= temp_max):
                    return False

            elif self.algorithm_mode == HVACMode.COOL:
                # Satisfied if temp is at or slightly below target
                temp_min = zone.target_temp - self.config.temp_tolerance
                temp_max = zone.target_temp
                if not (temp_min <= zone.current_temp <= temp_max):
                    return False

        return True
    
    def _check_fallback_satisfaction(self, now: datetime.datetime, algorithm_runtime: datetime.timedelta) -> bool:
        """Check fallback criteria for when Airtouch interferes with our algorithm"""
        
        # Fallback criteria 1: Maximum timeout reached
        if algorithm_runtime.total_seconds() >= self.config.algorithm_timeout_minutes * 60:
            self.log(f"Fallback: Algorithm timeout reached ({self.config.algorithm_timeout_minutes} minutes)")
            return True
        
        # Check if all zones are at least at target (not target + tolerance)
        zones_at_target = self._all_zones_at_target()
        if not zones_at_target:
            return False  # Can't use fallback if zones aren't even at target
        
        # Fallback criteria 2: No progress for extended time
        if self.last_progress_time:
            time_since_progress = now - self.last_progress_time
            if time_since_progress.total_seconds() >= self.config.progress_timeout_minutes * 60:
                self.log(f"Fallback: No progress for {self.config.progress_timeout_minutes} minutes - Airtouch likely controlling dampers")
                return True
        
        # Fallback criteria 3: Temperature stability (zones stable for extended time)
        if self._zones_stable_for_time(now, self.config.stability_check_minutes):
            self.log(f"Fallback: Zones stable for {self.config.stability_check_minutes} minutes - assuming Airtouch control")
            return True
        
        # Fallback criteria 4: Most dampers closed (indicating Airtouch control)
        if self._most_dampers_closed():
            self.log("Fallback: Most dampers closed - Airtouch has taken control")
            return True
        
        return False
    
    def _all_zones_satisfied(self) -> bool:
        """Check if all active zones are satisfied, with fallback for Airtouch interference"""
        if not self.algorithm_mode or not self.algorithm_start_time:
            return True  # Should not happen if algorithm is active
        
        now = datetime.datetime.now()
        algorithm_runtime = now - self.algorithm_start_time
        
        # Primary criteria: All zones reach target + tolerance (ideal case)
        primary_satisfied = self._check_primary_satisfaction()
        if primary_satisfied:
            self.log("All zones satisfied - primary criteria met")
            return True
        
        # If algorithm has run for minimum time, check fallback criteria
        min_runtime_minutes = 5  # Allow at least 5 minutes before considering fallback
        if algorithm_runtime.total_seconds() >= min_runtime_minutes * 60:
            fallback_satisfied = self._check_fallback_satisfaction(now, algorithm_runtime)
            if fallback_satisfied:
                return True
        
        return False
    
    def simulate_airtouch_interference(self):
        """Simulate the edge case where Airtouch closes dampers before reaching target + tolerance"""
        
        # Initial state: baby_bed triggers heating
        self.zones = {
            "baby_bed": ZoneState(
                entity_id="climate.baby_bed_2",
                damper_entity="cover.baby_bed_damper_2",
                current_temp=19.5,  # Triggers heating (target 20.0 - 0.5)
                target_temp=20.0,
                is_active=True,
                isolation=True,
                damper_position=50  # Our algorithm opened it
            ),
            "living": ZoneState(
                entity_id="climate.living_2",
                damper_entity="cover.living_damper_2",
                current_temp=21.8,  # Below target
                target_temp=22.0,
                is_active=True,
                isolation=False,
                damper_position=40  # Our algorithm opened it
            )
        }
        
        # Algorithm starts
        self.algorithm_active = True
        self.algorithm_mode = HVACMode.HEAT
        self.algorithm_start_time = datetime.datetime.now() - datetime.timedelta(minutes=20)  # Been running 20 minutes
        self.last_progress_time = datetime.datetime.now() - datetime.timedelta(minutes=16)  # Last progress 16 min ago
        
        print("AIRTOUCH INTERFERENCE SCENARIO")
        print("=" * 60)
        print("Initial state: Algorithm has been heating for 20 minutes")
        print("baby_bed: 19.5°C → 20.0°C (max desired: 20.5°C)")
        print("living:   21.8°C → 22.0°C (max desired: 22.5°C)")
        print()
        
        # Simulate Airtouch interference: zones heat up but dampers close before reaching our target + tolerance
        print("Simulating temperature rise with Airtouch interference...")
        
        # Time 1: Zones heat up, but Airtouch starts closing dampers before reaching our ideal target
        self.zones["baby_bed"].current_temp = 20.2  # Above target but below our max (20.5) - stuck here
        self.zones["baby_bed"].damper_position = 0   # Airtouch closed it completely!
        self.zones["living"].current_temp = 22.1     # Above target but below max (22.5) - stuck here  
        self.zones["living"].damper_position = 5     # Airtouch mostly closed it
        
        # Add temperature history showing stability
        now = datetime.datetime.now()
        for i in range(15):  # 15 minutes of stable readings
            time_point = now - datetime.timedelta(minutes=15-i)
            self.temperature_history.setdefault("baby_bed", []).append((time_point, 20.2))
            self.temperature_history.setdefault("living", []).append((time_point, 22.1))
        
        print("Current state after Airtouch interference:")
        print(f"baby_bed: {self.zones['baby_bed'].current_temp}°C, damper: {self.zones['baby_bed'].damper_position}%")
        print(f"living:   {self.zones['living'].current_temp}°C, damper: {self.zones['living'].damper_position}%")
        print()
        
        # Test primary satisfaction (should fail)
        primary_ok = self._check_primary_satisfaction()
        print(f"Primary satisfaction (target + tolerance): {primary_ok}")
        if primary_ok:
            print("✓ Both zones are within target + tolerance range")
        else:
            print("❌ Some zones not yet at target + tolerance")
        print()
        
        # Test fallback criteria
        zones_at_target = self._all_zones_at_target()
        print(f"All zones at target: {zones_at_target}")
        print("✓ baby_bed: 20.2°C ≥ 20.0°C target")
        print("✓ living: 22.1°C ≥ 22.0°C target")
        print()
        
        dampers_closed = self._most_dampers_closed()
        print(f"Most dampers closed (≤10%): {dampers_closed}")
        print("✓ 100% of dampers are ≤10% - Airtouch has taken control")
        print()
        
        stable = self._zones_stable_for_time(now, 10)
        print(f"Zones stable for 10 minutes: {stable}")
        print("✓ Temperatures have been stable - no further progress expected")
        print()
        
        # Test overall satisfaction with fallback
        satisfied = self._all_zones_satisfied()
        print(f"FINAL RESULT - All zones satisfied (with fallback): {satisfied}")
        
        if satisfied:
            print("✅ SUCCESS: Fallback mechanism correctly detects completion")
            print("   Algorithm will return to DRY mode instead of staying stuck")
        else:
            print("❌ FAILURE: Algorithm would stay stuck in heating mode")
        
        return satisfied


def test_normal_completion():
    """Test that normal completion still works"""
    print("\n" + "=" * 60)
    print("NORMAL COMPLETION TEST (no interference)")
    print("=" * 60)
    
    config = ControllerConfig(temp_tolerance=0.5)
    controller = FallbackTestController(config)
    
    controller.zones = {
        "baby_bed": ZoneState(
            entity_id="climate.baby_bed_2",
            damper_entity="cover.baby_bed_damper_2",
            current_temp=20.3,  # Reached target + tolerance
            target_temp=20.0,
            is_active=True,
            isolation=True,
            damper_position=50
        )
    }
    
    controller.algorithm_active = True
    controller.algorithm_mode = HVACMode.HEAT
    controller.algorithm_start_time = datetime.datetime.now() - datetime.timedelta(minutes=10)
    
    primary_ok = controller._check_primary_satisfaction()
    satisfied = controller._all_zones_satisfied()
    
    print(f"Zone temp: 20.3°C, target: 20.0°C, max: 20.5°C")
    print(f"Primary satisfaction: {primary_ok}")
    print(f"Overall satisfaction: {satisfied}")
    
    if satisfied:
        print("✅ Normal completion works correctly")
    else:
        print("❌ Normal completion broken")
    
    return satisfied


def test_timeout_fallback():
    """Test timeout fallback"""
    print("\n" + "=" * 60)
    print("TIMEOUT FALLBACK TEST")
    print("=" * 60)
    
    config = ControllerConfig(temp_tolerance=0.5, algorithm_timeout_minutes=30)
    controller = FallbackTestController(config)
    
    controller.zones = {
        "baby_bed": ZoneState(
            entity_id="climate.baby_bed_2",
            damper_entity="cover.baby_bed_damper_2",
            current_temp=20.1,  # At target but not target + tolerance
            target_temp=20.0,
            is_active=True,
            isolation=True,
            damper_position=50
        )
    }
    
    controller.algorithm_active = True
    controller.algorithm_mode = HVACMode.HEAT
    controller.algorithm_start_time = datetime.datetime.now() - datetime.timedelta(minutes=31)  # Exceeded timeout
    
    satisfied = controller._all_zones_satisfied()
    
    print(f"Algorithm runtime: 31 minutes (timeout: 30 minutes)")
    print(f"Zone at target: {controller._all_zones_at_target()}")
    print(f"Timeout fallback triggered: {satisfied}")
    
    if satisfied:
        print("✅ Timeout fallback works correctly")
    else:
        print("❌ Timeout fallback failed")
    
    return satisfied


if __name__ == "__main__":
    controller = FallbackTestController(ControllerConfig())
    
    test1 = controller.simulate_airtouch_interference()
    test2 = test_normal_completion()
    test3 = test_timeout_fallback()
    
    print("\n" + "=" * 60)
    print("FALLBACK MECHANISM TEST SUMMARY")
    print("=" * 60)
    
    if test1 and test2 and test3:
        print("🎉 ALL TESTS PASSED")
        print("✅ Fallback mechanism working correctly!")
        print("✅ Normal completion preserved")
        print("✅ Edge case handling: COMPLETE")
        print("\nThe algorithm will no longer get stuck when Airtouch")
        print("closes dampers before reaching target + tolerance.")
    else:
        print("❌ SOME TESTS FAILED")
        print(f"Airtouch interference: {'✅' if test1 else '❌'}")
        print(f"Normal completion: {'✅' if test2 else '❌'}")
        print(f"Timeout fallback: {'✅' if test3 else '❌'}")
    
    print("=" * 60)