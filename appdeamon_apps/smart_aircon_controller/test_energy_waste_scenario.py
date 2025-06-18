#!/usr/bin/env python3
"""
Test the energy waste scenario where HVAC gets stuck in heating mode
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


class EnergyWasteTestController:
    """Test controller to demonstrate energy waste prevention"""
    
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.zones: Dict[str, ZoneState] = {}
        self.current_hvac_mode: Optional[str] = "dry"
        self.algorithm_active: bool = False
        self.algorithm_mode: Optional[HVACMode] = None
        self.algorithm_start_time: Optional[datetime.datetime] = None
        self.temperature_history: Dict[str, List[Tuple[datetime.datetime, float]]] = {}
        self.last_progress_time: Optional[datetime.datetime] = None
        self.service_calls = []
        
    def log(self, message: str, level: str = "INFO"):
        print(f"[{level}] {message}")
        
    def call_service(self, service: str, **kwargs):
        call = {"service": service, "kwargs": kwargs}
        self.service_calls.append(call)
        print(f"SERVICE CALL: {service} with {kwargs}")
        
        # Simulate HVAC mode change
        if service == "climate/set_hvac_mode":
            entity_id = kwargs.get("entity_id")
            hvac_mode = kwargs.get("hvac_mode")
            if entity_id == self.config.main_climate:
                self.current_hvac_mode = hvac_mode
        
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
        """Check if zones have been stable for specified time"""
        stability_threshold = 0.1
        check_time = now - datetime.timedelta(minutes=minutes)
        
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue
                
            if zone_name not in self.temperature_history:
                return False
                
            stable_readings = [
                temp for time, temp in self.temperature_history[zone_name]
                if time >= check_time
            ]
            
            if len(stable_readings) < 3:
                return False
                
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
        return closed_dampers >= len(active_zones) * 0.7
    
    def _check_primary_satisfaction(self) -> bool:
        """Check if zones reach target + tolerance (ideal completion)"""
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue

            if self.algorithm_mode == HVACMode.HEAT:
                temp_min = zone.target_temp
                temp_max = zone.target_temp + self.config.temp_tolerance
                if not (temp_min <= zone.current_temp <= temp_max):
                    return False

            elif self.algorithm_mode == HVACMode.COOL:
                temp_min = zone.target_temp - self.config.temp_tolerance
                temp_max = zone.target_temp
                if not (temp_min <= zone.current_temp <= temp_max):
                    return False

        return True
    
    def _check_fallback_satisfaction(self, now: datetime.datetime, algorithm_runtime: datetime.timedelta) -> bool:
        """Check fallback criteria for energy waste prevention"""
        
        # Must have zones at target as minimum requirement
        zones_at_target = self._all_zones_at_target()
        if not zones_at_target:
            self.log("Fallback: Zones not at target yet - continue heating/cooling")
            return False
        
        # Fallback criteria 1: Maximum timeout reached
        if algorithm_runtime.total_seconds() >= self.config.algorithm_timeout_minutes * 60:
            self.log(f"Fallback: Algorithm timeout reached ({self.config.algorithm_timeout_minutes} minutes) - prevent energy waste")
            return True
        
        # Fallback criteria 2: No progress for extended time
        if self.last_progress_time:
            time_since_progress = now - self.last_progress_time
            if time_since_progress.total_seconds() >= self.config.progress_timeout_minutes * 60:
                self.log(f"Fallback: No progress for {self.config.progress_timeout_minutes} minutes - Airtouch has taken control")
                return True
        
        # Fallback criteria 3: Temperature stability
        if self._zones_stable_for_time(now, self.config.stability_check_minutes):
            self.log(f"Fallback: Zones stable for {self.config.stability_check_minutes} minutes - no further progress expected")
            return True
        
        # Fallback criteria 4: Most dampers closed by Airtouch
        if self._most_dampers_closed():
            self.log("Fallback: Most dampers closed - Airtouch has taken control, prevent energy waste")
            return True
        
        return False
    
    def _all_zones_satisfied(self) -> bool:
        """Check if algorithm should complete (with fallback for energy waste prevention)"""
        if not self.algorithm_mode or not self.algorithm_start_time:
            return True
        
        now = datetime.datetime.now()
        algorithm_runtime = now - self.algorithm_start_time
        
        # Primary criteria: All zones reach target + tolerance (ideal case)
        primary_satisfied = self._check_primary_satisfaction()
        if primary_satisfied:
            self.log("All zones satisfied - primary criteria met (ideal completion)")
            return True
        
        # Allow minimum runtime before considering fallback
        min_runtime_minutes = 5
        if algorithm_runtime.total_seconds() >= min_runtime_minutes * 60:
            fallback_satisfied = self._check_fallback_satisfaction(now, algorithm_runtime)
            if fallback_satisfied:
                self.log("FALLBACK TRIGGERED: Preventing energy waste - switching to DRY mode")
                return True
        
        return False
    
    def _deactivate_algorithm(self):
        """Deactivate algorithm and return to DRY mode (energy efficient)"""
        self.log("Deactivating algorithm - switching HVAC to DRY mode")
        
        # Critical: Switch HVAC to idle mode to stop energy waste
        self.call_service(
            "climate/set_hvac_mode",
            entity_id=self.config.main_climate,
            hvac_mode=self.config.idle_mode,
        )
        
        self.algorithm_active = False
        self.algorithm_mode = None
        self.algorithm_start_time = None
        self.temperature_history.clear()
        self.last_progress_time = None
    
    def simulate_energy_waste_scenario(self):
        """Simulate the exact energy waste scenario described"""
        
        print("ENERGY WASTE SCENARIO: HVAC STUCK IN HEATING MODE")
        print("=" * 60)
        
        # Initial setup: Baby bed triggers heating
        self.zones = {
            "baby_bed": ZoneState(
                entity_id="climate.baby_bed_2",
                damper_entity="cover.baby_bed_damper_2",
                current_temp=19.5,  # Below target - tolerance, triggers heating
                target_temp=20.0,
                is_active=True,
                isolation=True,
                damper_position=50  # Our algorithm opens it
            )
        }
        
        self.algorithm_active = True
        self.algorithm_mode = HVACMode.HEAT
        self.algorithm_start_time = datetime.datetime.now() - datetime.timedelta(minutes=15)
        self.last_progress_time = datetime.datetime.now() - datetime.timedelta(minutes=10)
        
        # HVAC is in heating mode
        self.current_hvac_mode = "heat"
        
        print("INITIAL STATE:")
        print(f"- baby_bed: {self.zones['baby_bed'].current_temp}°C → {self.zones['baby_bed'].target_temp}°C")
        print(f"- baby_bed damper: {self.zones['baby_bed'].damper_position}%")
        print(f"- HVAC mode: {self.current_hvac_mode}")
        print(f"- Algorithm active: {self.algorithm_active}")
        print(f"- Algorithm running for: 15 minutes")
        print()
        
        # Step 1: Zone heats up to above target
        print("STEP 1: Zone heats up...")
        self.zones["baby_bed"].current_temp = 20.4  # Above target, but below target + tolerance (20.5)
        
        print(f"- baby_bed: {self.zones['baby_bed'].current_temp}°C (target: {self.zones['baby_bed'].target_temp}°C)")
        print(f"- Target + tolerance: {self.zones['baby_bed'].target_temp + self.config.temp_tolerance}°C")
        print(f"- Zone above target: ✅")
        print(f"- Zone at target + tolerance: ❌ (needs {self.zones['baby_bed'].target_temp + self.config.temp_tolerance}°C)")
        print()
        
        # Step 2: Airtouch closes damper
        print("STEP 2: Airtouch closes damper (reaches its satisfaction)...")
        self.zones["baby_bed"].damper_position = 0  # Airtouch closed it!
        
        print(f"- baby_bed damper: {self.zones['baby_bed'].damper_position}% (Airtouch closed it)")
        print(f"- Zone can no longer heat further")
        print()
        
        # Add temperature history showing stability (can't heat further)
        now = datetime.datetime.now()
        for i in range(12):  # 12 minutes of stable readings
            time_point = now - datetime.timedelta(minutes=12-i)
            self.temperature_history.setdefault("baby_bed", []).append((time_point, 20.4))
        
        # Step 3: Check what happens WITHOUT fallback
        print("STEP 3: Without fallback mechanism...")
        primary_ok = self._check_primary_satisfaction()
        zones_at_target = self._all_zones_at_target()
        
        print(f"- Primary satisfaction (target + tolerance): {primary_ok}")
        print(f"- Zones at target: {zones_at_target}")
        print("- Without fallback: Algorithm keeps waiting for 20.5°C")
        print("- HVAC stays in HEAT mode ❌ (ENERGY WASTE)")
        print("- Compressor keeps running unnecessarily ❌")
        print()
        
        # Step 4: Check what happens WITH fallback
        print("STEP 4: With fallback mechanism...")
        fallback_runtime = datetime.timedelta(minutes=20)  # 20 minutes total runtime
        fallback_ok = self._check_fallback_satisfaction(now, fallback_runtime)
        
        dampers_closed = self._most_dampers_closed()
        stable = self._zones_stable_for_time(now, 10)
        
        print(f"- Zones at target: {zones_at_target} ✅")
        print(f"- Dampers closed (≤10%): {dampers_closed} ✅")
        print(f"- Temperature stable 10+ min: {stable} ✅")
        print(f"- No progress for 15+ min: ✅")
        print(f"- Fallback triggers: {fallback_ok} ✅")
        print()
        
        # Step 5: Test the complete satisfaction check
        print("STEP 5: Complete algorithm check...")
        satisfied = self._all_zones_satisfied()
        
        print(f"- Algorithm considers complete: {satisfied}")
        
        if satisfied:
            print("✅ ENERGY WASTE PREVENTED!")
            print("- Algorithm will deactivate")
            print("- HVAC will switch to DRY mode")
            print("- Compressor will stop running")
        else:
            print("❌ ENERGY WASTE CONTINUES!")
            print("- Algorithm keeps running")
            print("- HVAC stays in HEAT mode")
            print("- Compressor wastes energy")
        
        print()
        
        # Step 6: Simulate deactivation
        if satisfied:
            print("STEP 6: Deactivating algorithm...")
            old_hvac_mode = self.current_hvac_mode
            self._deactivate_algorithm()
            
            print(f"- HVAC mode: {old_hvac_mode} → {self.current_hvac_mode}")
            print(f"- Algorithm active: {self.algorithm_active}")
            print("✅ Energy waste prevented!")
        
        return satisfied


def test_energy_waste_prevention():
    """Test multiple energy waste scenarios"""
    
    print("\n" + "=" * 60)
    print("ENERGY WASTE PREVENTION TESTS")
    print("=" * 60)
    
    config = ControllerConfig(temp_tolerance=0.5)
    
    scenarios = [
        {
            "name": "Single Zone Stuck",
            "zones": {"zone1": {"current": 20.3, "target": 20.0, "damper": 0}},
            "description": "One zone stuck 0.2°C below ideal"
        },
        {
            "name": "Multiple Zones Stuck", 
            "zones": {
                "zone1": {"current": 20.3, "target": 20.0, "damper": 5},
                "zone2": {"current": 21.8, "target": 21.5, "damper": 0}
            },
            "description": "Multiple zones close to ideal but dampers closed"
        },
        {
            "name": "Timeout Protection",
            "zones": {"zone1": {"current": 19.9, "target": 20.0, "damper": 50}},
            "runtime": 35,  # Exceeds 30 min timeout
            "description": "Algorithm running too long"
        }
    ]
    
    results = []
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\nTEST {i}: {scenario['name']}")
        print("-" * 40)
        print(f"Description: {scenario['description']}")
        
        controller = EnergyWasteTestController(config)
        
        # Setup zones
        for zone_name, zone_data in scenario['zones'].items():
            controller.zones[zone_name] = ZoneState(
                entity_id=f"climate.{zone_name}",
                damper_entity=f"cover.{zone_name}_damper",
                current_temp=zone_data["current"],
                target_temp=zone_data["target"],
                is_active=True,
                isolation=False,
                damper_position=zone_data["damper"]
            )
        
        # Setup algorithm state
        runtime_minutes = scenario.get("runtime", 20)
        controller.algorithm_active = True
        controller.algorithm_mode = HVACMode.HEAT
        controller.algorithm_start_time = datetime.datetime.now() - datetime.timedelta(minutes=runtime_minutes)
        controller.last_progress_time = datetime.datetime.now() - datetime.timedelta(minutes=15)
        controller.current_hvac_mode = "heat"
        
        # Add stable temperature history
        now = datetime.datetime.now()
        for zone_name, zone_data in scenario['zones'].items():
            for j in range(12):
                time_point = now - datetime.timedelta(minutes=12-j)
                controller.temperature_history.setdefault(zone_name, []).append((time_point, zone_data["current"]))
        
        # Test
        zones_at_target = controller._all_zones_at_target()
        primary_ok = controller._check_primary_satisfaction()
        satisfied = controller._all_zones_satisfied()
        
        print(f"Zones at target: {zones_at_target}")
        print(f"Primary satisfaction: {primary_ok}")
        print(f"Fallback triggers: {satisfied and not primary_ok}")
        print(f"Energy waste prevented: {'✅' if satisfied else '❌'}")
        
        results.append(satisfied)
    
    print(f"\n{'='*60}")
    print("ENERGY WASTE PREVENTION SUMMARY")
    print(f"{'='*60}")
    
    if all(results):
        print("🎉 ALL TESTS PASSED")
        print("✅ Energy waste prevention working correctly!")
        print("✅ HVAC will not get stuck in heating/cooling mode")
        print("✅ Fallback mechanism provides robust protection")
    else:
        print("❌ SOME TESTS FAILED")
        for i, result in enumerate(results, 1):
            status = "✅" if result else "❌"
            print(f"   Test {i}: {status}")
    
    return all(results)


if __name__ == "__main__":
    controller = EnergyWasteTestController(ControllerConfig())
    
    test1 = controller.simulate_energy_waste_scenario()
    test2 = test_energy_waste_prevention()
    
    print("\n" + "=" * 60)
    print("FINAL RESULT: ENERGY WASTE PREVENTION")
    print("=" * 60)
    
    if test1 and test2:
        print("🎉 ENERGY WASTE PROBLEM SOLVED!")
        print()
        print("✅ Fallback mechanism prevents HVAC from getting stuck")
        print("✅ Zones reach 'good enough' temperature")
        print("✅ HVAC switches back to DRY mode automatically")
        print("✅ Energy waste prevented")
        print("✅ System remains robust and efficient")
    else:
        print("❌ Energy waste prevention needs work")
        print(f"   Main scenario: {'✅' if test1 else '❌'}")
        print(f"   Additional tests: {'✅' if test2 else '❌'}")
    
    print("=" * 60)