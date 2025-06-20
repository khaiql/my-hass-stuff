#!/usr/bin/env python3
"""
Sensor Simulator for Smart Aircon Controller

This script helps you simulate different sensor states and scenarios
to test how the smart aircon controller reacts without affecting real devices.

Usage:
    python sensor_simulator.py --scenario heating_needed
    python sensor_simulator.py --custom
"""

import json
import time
import requests
import argparse
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class ZoneConfig:
    """Configuration for a simulated zone."""
    climate_entity: str
    damper_entity: str
    sensor_temp: str
    sensor_target: str


@dataclass
class Scenario:
    """A test scenario with predefined conditions."""
    name: str
    description: str
    conditions: Dict[str, Any]


# Predefined test scenarios
SCENARIOS = {
    "heating_needed": Scenario(
        name="Heating Needed",
        description="Multiple zones need heating - should activate HEAT mode",
        conditions={
            "main_climate_mode": "dry",
            "smart_hvac_mode": "heat",
            "controller_enabled": True,
            "dry_run": True,  # Enable dry run for safe testing
            "zones": {
                "lounge": {"current_temp": 18.5, "target_temp": 21.0, "active": True, "damper_position": 5},
                "bedroom": {"current_temp": 17.0, "target_temp": 20.0, "active": True, "damper_position": 5},
                "study": {"current_temp": 19.0, "target_temp": 19.0, "active": False, "damper_position": 0},
            }
        }
    ),
    
    "cooling_needed": Scenario(
        name="Cooling Needed", 
        description="Multiple zones need cooling - should activate COOL mode",
        conditions={
            "main_climate_mode": "fan",
            "smart_hvac_mode": "cool",
            "controller_enabled": True,
            "dry_run": True,
            "zones": {
                "lounge": {"current_temp": 26.5, "target_temp": 24.0, "active": True, "damper_position": 5},
                "bedroom": {"current_temp": 27.0, "target_temp": 23.0, "active": True, "damper_position": 5},
                "study": {"current_temp": 25.0, "target_temp": 25.0, "active": False, "damper_position": 0},
            }
        }
    ),
    
    "satisfied_zones": Scenario(
        name="All Zones Satisfied",
        description="All zones at target temperature - should switch to idle mode",
        conditions={
            "main_climate_mode": "heat",
            "smart_hvac_mode": "heat", 
            "controller_enabled": True,
            "dry_run": True,
            "zones": {
                "lounge": {"current_temp": 21.2, "target_temp": 21.0, "active": True, "damper_position": 50},
                "bedroom": {"current_temp": 20.1, "target_temp": 20.0, "active": True, "damper_position": 40},
                "study": {"current_temp": 19.0, "target_temp": 19.0, "active": False, "damper_position": 0},
            }
        }
    ),
    
    "mixed_zones": Scenario(
        name="Mixed Zone Conditions",
        description="Some zones satisfied, others need attention",
        conditions={
            "main_climate_mode": "dry",
            "smart_hvac_mode": "heat",
            "controller_enabled": True,
            "dry_run": True,
            "zones": {
                "lounge": {"current_temp": 21.0, "target_temp": 21.0, "active": True, "damper_position": 10},
                "bedroom": {"current_temp": 18.0, "target_temp": 20.5, "active": True, "damper_position": 5},
                "study": {"current_temp": 22.0, "target_temp": 19.0, "active": True, "damper_position": 5},
            }
        }
    ),
    
    "controller_disabled": Scenario(
        name="Controller Disabled",
        description="Controller is disabled - should not take any action",
        conditions={
            "main_climate_mode": "heat",
            "smart_hvac_mode": "heat",
            "controller_enabled": False,
            "dry_run": False,
            "zones": {
                "lounge": {"current_temp": 18.0, "target_temp": 22.0, "active": True, "damper_position": 5},
                "bedroom": {"current_temp": 17.0, "target_temp": 21.0, "active": True, "damper_position": 5},
            }
        }
    ),
    
    "no_active_zones": Scenario(
        name="No Active Zones",
        description="All zones are inactive - automation should do nothing",
        conditions={
            "main_climate_mode": "heat",
            "smart_hvac_mode": "heat",
            "controller_enabled": True,
            "dry_run": True,
            "zones": {
                "lounge": {"current_temp": 20.0, "target_temp": 21.0, "active": False, "damper_position": 0},
                "bedroom": {"current_temp": 19.0, "target_temp": 20.0, "active": False, "damper_position": 0},
                "study": {"current_temp": 18.0, "target_temp": 19.0, "active": False, "damper_position": 0},
            }
        }
    ),
}


class HASimulator:
    """Home Assistant entity simulator."""
    
    def __init__(self, ha_url: str, token: str):
        self.ha_url = ha_url.rstrip('/')
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def set_entity_state(self, entity_id: str, state: Any, attributes: Dict = None):
        """Set the state of an entity."""
        url = f"{self.ha_url}/api/states/{entity_id}"
        data = {
            'state': str(state),
            'attributes': attributes or {}
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            print(f"✅ Set {entity_id} = {state}")
            return True
        except Exception as e:
            print(f"❌ Error setting {entity_id}: {e}")
            return False
    
    def get_entity_state(self, entity_id: str):
        """Get the current state of an entity."""
        url = f"{self.ha_url}/api/states/{entity_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Error getting {entity_id}: {e}")
            return None


def apply_scenario(simulator: HASimulator, scenario: Scenario, zone_configs: Dict[str, ZoneConfig]):
    """Apply a test scenario to Home Assistant."""
    print(f"\n🎯 Applying scenario: {scenario.name}")
    print(f"📝 Description: {scenario.description}")
    print("-" * 60)
    
    conditions = scenario.conditions
    
    # Set controller configuration
    print("Setting controller configuration...")
    simulator.set_entity_state("input_boolean.smart_aircon_enabled", 
                             "on" if conditions["controller_enabled"] else "off")
    simulator.set_entity_state("input_select.smart_aircon_hvac_mode", 
                             conditions["smart_hvac_mode"])
    
    # Set main climate state
    print(f"Setting main climate to {conditions['main_climate_mode']}...")
    simulator.set_entity_state("climate.aircon", conditions["main_climate_mode"])
    
    # Set zone conditions
    print("Setting zone conditions...")
    for zone_name, zone_data in conditions["zones"].items():
        if zone_name in zone_configs:
            config = zone_configs[zone_name]
            
            # Set climate entity state and attributes
            climate_state = "heat" if zone_data["active"] else "off"
            climate_attrs = {
                "temperature": zone_data["target_temp"],
                "current_temperature": zone_data["current_temp"],
                "hvac_mode": climate_state,
                "hvac_modes": ["off", "heat", "cool", "dry", "fan"],
                "unit_of_measurement": "°C"
            }
            
            simulator.set_entity_state(config.climate_entity, climate_state, climate_attrs)
            
            # Set damper position
            damper_attrs = {
                "current_position": zone_data["damper_position"],
                "device_class": "damper"
            }
            damper_state = "open" if zone_data["damper_position"] > 0 else "closed"
            simulator.set_entity_state(config.damper_entity, damper_state, damper_attrs)
            
            print(f"  {zone_name}: {zone_data['current_temp']}°C -> {zone_data['target_temp']}°C, "
                  f"Active: {zone_data['active']}, Damper: {zone_data['damper_position']}%")
    
    print(f"\n✅ Scenario '{scenario.name}' applied successfully!")
    print("🔍 Check AppDaemon logs to see how the controller reacts")
    print("📝 Note: Dry run mode is configured in apps.yaml, not via Home Assistant entities")
    
    if conditions.get("dry_run"):
        print("🔥 This scenario was designed for DRY RUN MODE")
        print("   Make sure dry_run: true is set in your apps.yaml configuration")


def interactive_mode(simulator: HASimulator, zone_configs: Dict[str, ZoneConfig]):
    """Interactive mode for custom scenarios."""
    print("\n🛠️  Interactive Mode - Create Custom Scenario")
    print("=" * 50)
    
    # Get controller settings
    enabled = input("Enable controller? (y/n): ").lower().startswith('y')
    hvac_mode = input("Smart HVAC mode (heat/cool): ").lower()
    main_climate = input("Main climate mode (heat/cool/dry/fan/off): ").lower()
    
    # Set controller config
    simulator.set_entity_state("input_boolean.smart_aircon_enabled", "on" if enabled else "off")
    simulator.set_entity_state("input_select.smart_aircon_hvac_mode", hvac_mode)
    simulator.set_entity_state("climate.aircon", main_climate)
    
    # Configure zones
    print(f"\nConfiguring {len(zone_configs)} zones...")
    for zone_name, config in zone_configs.items():
        print(f"\n--- Zone: {zone_name} ---")
        active = input(f"Is {zone_name} active? (y/n): ").lower().startswith('y')
        
        if active:
            current_temp = float(input(f"Current temperature for {zone_name}: "))
            target_temp = float(input(f"Target temperature for {zone_name}: "))
            damper_pos = int(input(f"Damper position for {zone_name} (0-100): "))
            
            # Set climate entity
            climate_attrs = {
                "temperature": target_temp,
                "current_temperature": current_temp,
                "hvac_mode": "heat",
                "unit_of_measurement": "°C"
            }
            simulator.set_entity_state(config.climate_entity, "heat", climate_attrs)
            
            # Set damper
            damper_attrs = {"current_position": damper_pos}
            damper_state = "open" if damper_pos > 0 else "closed"
            simulator.set_entity_state(config.damper_entity, damper_state, damper_attrs)
        else:
            # Set zone as inactive
            simulator.set_entity_state(config.climate_entity, "off")
            simulator.set_entity_state(config.damper_entity, "closed", {"current_position": 0})
    
    print("\n✅ Custom scenario applied!")


def main():
    parser = argparse.ArgumentParser(description="Smart Aircon Controller Sensor Simulator")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), 
                       help="Apply a predefined scenario")
    parser.add_argument("--custom", action="store_true", 
                       help="Interactive mode for custom scenarios")
    parser.add_argument("--list", action="store_true", 
                       help="List available scenarios")
    parser.add_argument("--ha-url", default="http://homeassistant.local:8123",
                       help="Home Assistant URL")
    parser.add_argument("--token", help="Home Assistant Long-Lived Access Token")
    
    args = parser.parse_args()
    
    if args.list:
        print("📋 Available Test Scenarios:")
        print("=" * 50)
        for name, scenario in SCENARIOS.items():
            print(f"🎯 {name}")
            print(f"   {scenario.description}")
            print()
        return
    
    # Configuration - Update these to match your setup
    ZONE_CONFIGS = {
        "lounge": ZoneConfig(
            climate_entity="climate.lounge",
            damper_entity="cover.lounge_damper", 
            sensor_temp="sensor.lounge_temperature",
            sensor_target="sensor.smart_aircon_lounge_target_temp"
        ),
        "bedroom": ZoneConfig(
            climate_entity="climate.bedroom",
            damper_entity="cover.bedroom_damper",
            sensor_temp="sensor.bedroom_temperature", 
            sensor_target="sensor.smart_aircon_bedroom_target_temp"
        ),
        "study": ZoneConfig(
            climate_entity="climate.study",
            damper_entity="cover.study_damper",
            sensor_temp="sensor.study_temperature",
            sensor_target="sensor.smart_aircon_study_target_temp"
        ),
    }
    
    # Get token
    token = args.token
    if not token:
        print("Please provide a Home Assistant Long-Lived Access Token:")
        print("1. Go to your Home Assistant profile")
        print("2. Scroll to 'Long-Lived Access Tokens'")
        print("3. Click 'Create Token'")
        token = input("Enter token: ").strip()
    
    if not token:
        print("❌ Token is required")
        return
    
    simulator = HASimulator(args.ha_url, token)
    
    if args.scenario:
        scenario = SCENARIOS[args.scenario]
        apply_scenario(simulator, scenario, ZONE_CONFIGS)
    elif args.custom:
        interactive_mode(simulator, ZONE_CONFIGS)
    else:
        print("Please specify --scenario, --custom, or --list")
        print("Use --help for more information")


if __name__ == "__main__":
    main() 