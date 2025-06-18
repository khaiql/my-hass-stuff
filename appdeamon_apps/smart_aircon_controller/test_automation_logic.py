#!/usr/bin/env python3
"""
Test script to simulate the smart aircon controller automation logic
with various scenarios to ensure it works correctly.
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
    """Represents the current state of a zone"""
    entity_id: str
    damper_entity: str
    current_temp: float
    target_temp: float
    is_active: bool
    isolation: bool = False
    damper_position: int = 0


@dataclass
class ControllerConfig:
    """Configuration for the smart aircon controller"""
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


class MockSmartAirconController:
    """Mock version of the smart aircon controller for testing"""
    
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.zones: Dict[str, ZoneState] = {}
        self.current_hvac_mode: Optional[str] = "dry"
        self.algorithm_active: bool = False
        self.algorithm_mode: Optional[HVACMode] = None
        self.service_calls = []  # Track service calls
        self.log_messages = []  # Track log messages
        
    def log(self, message: str, level: str = "INFO"):
        """Mock logging"""
        self.log_messages.append(f"[{level}] {message}")
        print(f"[{level}] {message}")
        
    def call_service(self, service: str, **kwargs):
        """Mock service calls"""
        call = {"service": service, "kwargs": kwargs}
        self.service_calls.append(call)
        print(f"SERVICE CALL: {service} with {kwargs}")
        
        # Simulate HVAC mode change
        if service == "climate/set_hvac_mode":
            entity_id = kwargs.get("entity_id")
            hvac_mode = kwargs.get("hvac_mode")
            if entity_id == self.config.main_climate:
                self.current_hvac_mode = hvac_mode
                
    def _analyze_zones_for_heating(self) -> List[str]:
        """Analyze zones to determine which need heating"""
        zones_needing_heating = []
        
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue
                
            # Check if zone needs heating
            if zone.current_temp < (zone.target_temp - self.config.temp_tolerance):
                zones_needing_heating.append(zone_name)
                self.log(
                    f"Zone {zone_name} needs heating: {zone.current_temp}°C < {zone.target_temp - self.config.temp_tolerance}°C"
                )
                
        return zones_needing_heating
    
    def _analyze_zones_for_cooling(self) -> List[str]:
        """Analyze zones to determine which need cooling"""
        zones_needing_cooling = []
        
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue
                
            # Check if zone needs cooling
            if zone.current_temp > (zone.target_temp + self.config.temp_tolerance):
                zones_needing_cooling.append(zone_name)
                self.log(
                    f"Zone {zone_name} needs cooling: {zone.current_temp}°C > {zone.target_temp + self.config.temp_tolerance}°C"
                )
                
        return zones_needing_cooling
    
    def _calculate_damper_positions(self, trigger_zones: List[str], mode: HVACMode) -> Dict[str, int]:
        """Calculate optimal damper positions for all zones"""
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
                    temp_diff = zone.target_temp - zone.current_temp
                else:  # COOL mode
                    temp_diff = zone.current_temp - zone.target_temp
                    
                if temp_diff > self.config.temp_tolerance:
                    # Zone could benefit from heating/cooling
                    damper_positions[zone_name] = self.config.secondary_damper_percent
                elif temp_diff > -self.config.temp_tolerance:
                    # Zone is close to target, minimal damper opening
                    damper_positions[zone_name] = self.config.overflow_damper_percent
                else:
                    # Zone is above target (for heat) or below target (for cool)
                    damper_positions[zone_name] = 0
                    
        return damper_positions
    
    def _apply_damper_positions(self, positions: Dict[str, int]):
        """Apply calculated damper positions"""
        for zone_name, position in positions.items():
            if zone_name not in self.zones:
                continue
                
            zone = self.zones[zone_name]
            if position > 0:
                self.call_service(
                    "cover/set_cover_position",
                    entity_id=zone.damper_entity,
                    position=position,
                )
                self.log(f"Set {zone_name} damper to {position}%")
                zone.damper_position = position
            else:
                self.call_service("cover/close_cover", entity_id=zone.damper_entity)
                self.log(f"Closed {zone_name} damper")
                zone.damper_position = 0
    
    def _set_hvac_mode(self, mode: HVACMode):
        """Set the main HVAC system mode"""
        if self.current_hvac_mode != mode.value:
            self.call_service(
                "climate/set_hvac_mode",
                entity_id=self.config.main_climate,
                hvac_mode=mode.value,
            )
            self.current_hvac_mode = mode.value
            self.log(f"Set HVAC mode to {mode.value}")
    
    def _execute_smart_algorithm(self, trigger_zones: List[str], mode: HVACMode):
        """Execute the smart heating/cooling algorithm"""
        self.log(f"Executing smart {mode.value} algorithm for zones: {trigger_zones}")
        
        # Calculate damper positions for all active zones
        damper_positions = self._calculate_damper_positions(trigger_zones, mode)
        
        # Set HVAC to the appropriate mode for energy efficiency
        self._set_hvac_mode(mode)
        
        # Apply damper positions
        self._apply_damper_positions(damper_positions)
        
        self.algorithm_active = True
        self.algorithm_mode = mode
    
    def _all_zones_satisfied(self) -> bool:
        """Check if all active zones are within their target temperature range"""
        if not self.algorithm_mode:
            return True
            
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
    
    def _deactivate_algorithm(self):
        """Deactivate the smart algorithm and return to idle mode"""
        self.log("All zones satisfied, deactivating algorithm")
        
        # Set HVAC to idle mode
        self._set_hvac_mode(HVACMode.DRY)
        
        self.algorithm_active = False
        self.algorithm_mode = None
    
    def periodic_check(self):
        """Simulate the periodic check - main automation logic"""
        self.log("=== PERIODIC CHECK START ===")
        
        if not self.config.enabled:
            self.log("Controller disabled, skipping periodic check")
            return
            
        # Get current HVAC mode for logging/status only
        self.log(f"Current HVAC mode: {self.current_hvac_mode}, Smart HVAC mode: {self.config.smart_hvac_mode}")
        
        # Determine which zones need attention based on smart_hvac_mode (desired mode)
        if self.config.smart_hvac_mode == "heat":
            zones_needing_attention = self._analyze_zones_for_heating()
            target_mode = HVACMode.HEAT
        elif self.config.smart_hvac_mode == "cool":
            zones_needing_attention = self._analyze_zones_for_cooling()
            target_mode = HVACMode.COOL
        else:
            self.log(f"Invalid smart_hvac_mode: {self.config.smart_hvac_mode}", level="ERROR")
            return
            
        self.log(f"Zones needing {self.config.smart_hvac_mode}: {zones_needing_attention}")
        
        # If algorithm is already running in the correct mode
        if self.algorithm_active and self.algorithm_mode == target_mode:
            if self._all_zones_satisfied():
                self.log("Current cycle complete.")
                self._deactivate_algorithm()
            elif zones_needing_attention:
                self.log(f"{target_mode.value.title()} cycle continues. Re-evaluating damper positions.")
                self._execute_smart_algorithm(zones_needing_attention, target_mode)
            return
            
        # If algorithm is running in wrong mode, deactivate it
        if self.algorithm_active and self.algorithm_mode != target_mode:
            self.log(f"Smart HVAC mode changed from {self.algorithm_mode.value} to {target_mode.value}, deactivating algorithm")
            self._deactivate_algorithm()
            return
            
        # If algorithm is NOT active, start it if zones need attention
        if zones_needing_attention:
            self._execute_smart_algorithm(zones_needing_attention, target_mode)
            
        self.log("=== PERIODIC CHECK END ===\n")


def create_test_zones() -> Dict[str, ZoneState]:
    """Create test zones based on the original requirements"""
    return {
        "baby_bed": ZoneState(
            entity_id="climate.baby_bed_2",
            damper_entity="cover.baby_bed_damper_2",
            current_temp=19.7,
            target_temp=20.0,
            is_active=True,
            isolation=True  # Baby room is isolated
        ),
        "master_bed": ZoneState(
            entity_id="climate.master_bed_",
            damper_entity="cover.master_bed_damper_2",
            current_temp=21.2,
            target_temp=19.0,
            is_active=True,
            isolation=False
        ),
        "living": ZoneState(
            entity_id="climate.living_2",
            damper_entity="cover.living_damper_2",
            current_temp=21.6,
            target_temp=22.0,
            is_active=True,
            isolation=False
        ),
        "guest_bed": ZoneState(
            entity_id="climate.guest_bed_2",
            damper_entity="cover.guest_bed_damper_2",
            current_temp=20.2,
            target_temp=20.0,
            is_active=False,  # Start as inactive
            isolation=False
        )
    }


def print_scenario_header(title: str):
    """Print scenario header"""
    print(f"\n{'='*60}")
    print(f"SCENARIO: {title}")
    print(f"{'='*60}")


def print_zone_status(controller: MockSmartAirconController):
    """Print current zone status"""
    print("\nCURRENT ZONE STATUS:")
    print("-" * 50)
    for zone_name, zone in controller.zones.items():
        status = "ACTIVE" if zone.is_active else "INACTIVE"
        isolation = "ISOLATED" if zone.isolation else "SHARED"
        print(f"{zone_name:12} | {zone.current_temp:5.1f}°C → {zone.target_temp:5.1f}°C | {status:8} | {isolation:8} | Damper: {zone.damper_position:2d}%")


def run_heating_scenario():
    """Test heating scenario"""
    print_scenario_header("HEATING SCENARIO - Multiple Zones Need Heating")
    
    config = ControllerConfig(smart_hvac_mode="heat", temp_tolerance=0.5)
    controller = MockSmartAirconController(config)
    controller.zones = create_test_zones()
    
    # Modify zones to need heating
    controller.zones["baby_bed"].current_temp = 19.2  # Needs heating (target 20.0, tolerance 0.5)
    controller.zones["master_bed"].current_temp = 18.2  # Needs heating (target 19.0, tolerance 0.5)
    controller.zones["living"].current_temp = 21.2  # Needs heating (target 22.0, tolerance 0.5)
    controller.zones["guest_bed"].is_active = True
    controller.zones["guest_bed"].current_temp = 19.2  # Needs heating (target 20.0, tolerance 0.5)
    
    print_zone_status(controller)
    
    # Run first periodic check
    print("\n--- FIRST PERIODIC CHECK ---")
    controller.periodic_check()
    
    print_zone_status(controller)
    print(f"Algorithm Active: {controller.algorithm_active}")
    print(f"Algorithm Mode: {controller.algorithm_mode}")
    print(f"Current HVAC Mode: {controller.current_hvac_mode}")
    
    # Simulate temperature changes after heating
    print("\n--- SIMULATING TEMPERATURE RISE ---")
    controller.zones["baby_bed"].current_temp = 20.3  # Satisfied
    controller.zones["master_bed"].current_temp = 19.3  # Satisfied
    controller.zones["living"].current_temp = 21.8  # Still needs heating
    controller.zones["guest_bed"].current_temp = 19.8  # Still needs heating
    
    print_zone_status(controller)
    
    # Run second periodic check
    print("\n--- SECOND PERIODIC CHECK ---")
    controller.periodic_check()
    
    print_zone_status(controller)
    print(f"Algorithm Active: {controller.algorithm_active}")
    print(f"Algorithm Mode: {controller.algorithm_mode}")
    print(f"Current HVAC Mode: {controller.current_hvac_mode}")
    
    # All zones satisfied
    print("\n--- SIMULATING ALL ZONES SATISFIED ---")
    controller.zones["living"].current_temp = 22.2  # Satisfied
    controller.zones["guest_bed"].current_temp = 20.2  # Satisfied
    
    print_zone_status(controller)
    
    # Run third periodic check
    print("\n--- THIRD PERIODIC CHECK ---")
    controller.periodic_check()
    
    print_zone_status(controller)
    print(f"Algorithm Active: {controller.algorithm_active}")
    print(f"Algorithm Mode: {controller.algorithm_mode}")
    print(f"Current HVAC Mode: {controller.current_hvac_mode}")


def run_cooling_scenario():
    """Test cooling scenario"""
    print_scenario_header("COOLING SCENARIO - Multiple Zones Need Cooling")
    
    config = ControllerConfig(smart_hvac_mode="cool", temp_tolerance=0.5)
    controller = MockSmartAirconController(config)
    controller.zones = create_test_zones()
    
    # Modify zones to need cooling
    controller.zones["baby_bed"].current_temp = 20.8  # Needs cooling (target 20.0, tolerance 0.5)
    controller.zones["master_bed"].current_temp = 19.8  # Needs cooling (target 19.0, tolerance 0.5)
    controller.zones["living"].current_temp = 22.8  # Needs cooling (target 22.0, tolerance 0.5)
    controller.zones["guest_bed"].is_active = True
    controller.zones["guest_bed"].current_temp = 20.8  # Needs cooling (target 20.0, tolerance 0.5)
    
    print_zone_status(controller)
    
    # Run first periodic check
    print("\n--- FIRST PERIODIC CHECK ---")
    controller.periodic_check()
    
    print_zone_status(controller)
    print(f"Algorithm Active: {controller.algorithm_active}")
    print(f"Algorithm Mode: {controller.algorithm_mode}")
    print(f"Current HVAC Mode: {controller.current_hvac_mode}")


def run_isolation_scenario():
    """Test zone isolation scenario"""
    print_scenario_header("ISOLATION SCENARIO - Baby Room Isolation")
    
    config = ControllerConfig(smart_hvac_mode="heat", temp_tolerance=0.5)
    controller = MockSmartAirconController(config)
    controller.zones = create_test_zones()
    
    # Only master_bed needs heating, baby_bed is OK
    controller.zones["baby_bed"].current_temp = 20.2  # Satisfied
    controller.zones["master_bed"].current_temp = 18.2  # Needs heating
    controller.zones["living"].current_temp = 21.8  # Satisfied
    controller.zones["guest_bed"].is_active = False
    
    print_zone_status(controller)
    
    # Run periodic check
    print("\n--- PERIODIC CHECK ---")
    controller.periodic_check()
    
    print_zone_status(controller)
    print(f"Algorithm Active: {controller.algorithm_active}")
    print(f"Algorithm Mode: {controller.algorithm_mode}")
    print(f"Current HVAC Mode: {controller.current_hvac_mode}")
    
    print("\nNote: Baby bed should have 0% damper due to isolation when not a trigger zone")


def run_mode_change_scenario():
    """Test smart HVAC mode change scenario"""
    print_scenario_header("MODE CHANGE SCENARIO - Heat to Cool")
    
    config = ControllerConfig(smart_hvac_mode="heat", temp_tolerance=0.5)
    controller = MockSmartAirconController(config)
    controller.zones = create_test_zones()
    
    # Start with heating scenario
    controller.zones["baby_bed"].current_temp = 19.2  # Needs heating
    controller.zones["master_bed"].current_temp = 18.2  # Needs heating
    controller.zones["living"].current_temp = 21.2  # Needs heating
    controller.zones["guest_bed"].is_active = False
    
    print_zone_status(controller)
    
    # Run periodic check - should start heating
    print("\n--- PERIODIC CHECK (HEATING MODE) ---")
    controller.periodic_check()
    
    print(f"Algorithm Active: {controller.algorithm_active}")
    print(f"Algorithm Mode: {controller.algorithm_mode}")
    print(f"Current HVAC Mode: {controller.current_hvac_mode}")
    
    # Change to cooling mode
    print("\n--- CHANGING SMART HVAC MODE TO COOL ---")
    controller.config.smart_hvac_mode = "cool"
    
    # Run periodic check - should deactivate heating algorithm
    print("\n--- PERIODIC CHECK (AFTER MODE CHANGE) ---")
    controller.periodic_check()
    
    print(f"Algorithm Active: {controller.algorithm_active}")
    print(f"Algorithm Mode: {controller.algorithm_mode}")
    print(f"Current HVAC Mode: {controller.current_hvac_mode}")


if __name__ == "__main__":
    print("SMART AIRCON CONTROLLER - AUTOMATION LOGIC TEST")
    print("=" * 60)
    
    # Run test scenarios
    run_heating_scenario()
    run_cooling_scenario()
    run_isolation_scenario()
    run_mode_change_scenario()
    
    print("\n" + "=" * 60)
    print("ALL SCENARIOS COMPLETED")
    print("=" * 60)