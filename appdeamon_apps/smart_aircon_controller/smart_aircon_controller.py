import appdaemon.plugins.hass.hassapi as hass
import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


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
    temp_sensor: str
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


class SmartAirconController(hass.Hass):
    """
    Smart Aircon Controller for Airtouch 5 System
    
    Implements energy-efficient heating/cooling by coordinating multiple zones
    and leveraging shared heating when one zone triggers.
    """

    def initialize(self):
        """Initialize the smart aircon controller"""
        self.log("Initializing Smart Aircon Controller")
        
        # Load configuration
        self._load_config()
        
        # Initialize state tracking
        self.zones: Dict[str, ZoneState] = {}
        self.current_hvac_mode: Optional[str] = None
        self.algorithm_active: bool = False
        self.last_check_time: Optional[datetime.datetime] = None
        
        # Load zone configurations
        self._initialize_zones()
        
        # Set up periodic checking
        if self.config.enabled:
            self.run_every(
                self._periodic_check,
                datetime.datetime.now() + datetime.timedelta(seconds=10),
                self.config.check_interval
            )
        
        self.log(f"Smart Aircon Controller initialized with {len(self.zones)} zones")

    def _load_config(self):
        """Load configuration from apps.yaml"""
        self.config = ControllerConfig(
            enabled=self.args.get("enabled", True),
            check_interval=self.args.get("check_interval", 30),
            temp_tolerance=self.args.get("temp_tolerance", 0.5),
            main_climate=self.args.get("main_climate", "climate.aircon"),
            primary_damper_percent=self.args.get("primary_damper_percent", 50),
            secondary_damper_percent=self.args.get("secondary_damper_percent", 40),
            overflow_damper_percent=self.args.get("overflow_damper_percent", 10),
            heating_mode=self.args.get("heating_mode", "heat"),
            idle_mode=self.args.get("idle_mode", "dry"),
            cooling_mode=self.args.get("cooling_mode", "cool")
        )

    def _initialize_zones(self):
        """Initialize zone configurations from config"""
        zones_config = self.args.get("zones", {})
        
        for zone_name, zone_config in zones_config.items():
            try:
                # Validate required entities exist
                climate_entity = zone_config["climate_entity"]
                damper_entity = zone_config["damper_entity"]
                temp_sensor = zone_config["temp_sensor"]
                
                if not self._entity_exists(climate_entity):
                    self.log(f"Warning: Climate entity {climate_entity} not found", level="WARNING")
                    continue
                    
                if not self._entity_exists(damper_entity):
                    self.log(f"Warning: Damper entity {damper_entity} not found", level="WARNING")
                    continue
                    
                if not self._entity_exists(temp_sensor):
                    self.log(f"Warning: Temperature sensor {temp_sensor} not found", level="WARNING")
                    continue
                
                # Create zone state
                zone_state = ZoneState(
                    entity_id=climate_entity,
                    damper_entity=damper_entity,
                    temp_sensor=temp_sensor,
                    current_temp=0.0,
                    target_temp=0.0,
                    is_active=False,
                    isolation=zone_config.get("isolation", False)
                )
                
                self.zones[zone_name] = zone_state
                self.log(f"Initialized zone: {zone_name}")
                
            except KeyError as e:
                self.log(f"Error initializing zone {zone_name}: Missing config {e}", level="ERROR")
            except Exception as e:
                self.log(f"Error initializing zone {zone_name}: {e}", level="ERROR")

    def _entity_exists(self, entity_id: str) -> bool:
        """Check if an entity exists in Home Assistant"""
        try:
            state = self.get_state(entity_id)
            return state is not None
        except:
            return False

    def _periodic_check(self, kwargs):
        """Periodic check function called every check_interval seconds"""
        if not self.config.enabled:
            return
            
        try:
            self.last_check_time = datetime.datetime.now()
            self._update_zone_states()
            
            # Check if algorithm should trigger
            zones_needing_action = self._analyze_zones()
            
            if zones_needing_action:
                self._execute_smart_algorithm(zones_needing_action)
            elif self.algorithm_active:
                # Check if we should deactivate
                if self._all_zones_satisfied():
                    self._deactivate_algorithm()
                    
        except Exception as e:
            self.log(f"Error in periodic check: {e}", level="ERROR")

    def _update_zone_states(self):
        """Update current state of all zones"""
        for zone_name, zone in self.zones.items():
            try:
                # Get climate entity state
                climate_state = self.get_state(zone.entity_id)
                if climate_state in ["unavailable", "unknown", None]:
                    continue
                    
                # Update zone state
                zone.is_active = climate_state not in ["off", "unavailable"]
                
                # Get target temperature
                climate_attrs = self.get_state(zone.entity_id, attribute="all")
                if climate_attrs and "attributes" in climate_attrs:
                    attrs = climate_attrs["attributes"]
                    zone.target_temp = float(attrs.get("temperature", 0))
                
                # Get current temperature
                temp_state = self.get_state(zone.temp_sensor)
                if temp_state and temp_state not in ["unavailable", "unknown"]:
                    zone.current_temp = float(temp_state)
                
                # Get damper position
                damper_state = self.get_state(zone.damper_entity, attribute="current_position")
                if damper_state is not None:
                    zone.damper_position = int(damper_state)
                    
            except Exception as e:
                self.log(f"Error updating zone {zone_name}: {e}", level="ERROR")

    def _analyze_zones(self) -> List[str]:
        """Analyze zones to determine which need heating/cooling"""
        zones_needing_action = []
        
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue
                
            # Check if zone needs heating
            if zone.current_temp < (zone.target_temp - self.config.temp_tolerance):
                zones_needing_action.append(zone_name)
                self.log(f"Zone {zone_name} needs heating: {zone.current_temp}°C < {zone.target_temp - self.config.temp_tolerance}°C")
            
            # Check if zone needs cooling (for future implementation)
            elif zone.current_temp > (zone.target_temp + self.config.temp_tolerance):
                # TODO: Implement cooling logic
                pass
                
        return zones_needing_action

    def _execute_smart_algorithm(self, trigger_zones: List[str]):
        """Execute the smart heating algorithm"""
        self.log(f"Executing smart algorithm for zones: {trigger_zones}")
        
        # Calculate damper positions for all active zones
        damper_positions = self._calculate_damper_positions(trigger_zones)
        
        # Set HVAC to heating mode
        self._set_hvac_mode(HVACMode.HEAT)
        
        # Apply damper positions
        self._apply_damper_positions(damper_positions)
        
        self.algorithm_active = True

    def _calculate_damper_positions(self, trigger_zones: List[str]) -> Dict[str, int]:
        """Calculate optimal damper positions for all zones"""
        damper_positions = {}
        
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                damper_positions[zone_name] = 0
                continue
            
            if zone.isolation and zone_name not in trigger_zones:
                # Isolated zones don't participate in shared heating
                damper_positions[zone_name] = 0
                continue
            
            if zone_name in trigger_zones:
                # Primary trigger zone gets full damper opening
                damper_positions[zone_name] = self.config.primary_damper_percent
            else:
                # Calculate damper position for secondary zones
                temp_diff = zone.target_temp - zone.current_temp
                
                if temp_diff > 0:
                    # Zone could benefit from heating
                    damper_positions[zone_name] = self.config.secondary_damper_percent
                elif temp_diff > -self.config.temp_tolerance:
                    # Zone is close to target, minimal damper opening
                    damper_positions[zone_name] = self.config.overflow_damper_percent
                else:
                    # Zone is above target, keep damper closed
                    damper_positions[zone_name] = 0
                    
        return damper_positions

    def _apply_damper_positions(self, positions: Dict[str, int]):
        """Apply calculated damper positions"""
        for zone_name, position in positions.items():
            if zone_name not in self.zones:
                continue
                
            zone = self.zones[zone_name]
            try:
                if position > 0:
                    self.call_service(
                        "cover/set_cover_position",
                        entity_id=zone.damper_entity,
                        position=position
                    )
                    self.log(f"Set {zone_name} damper to {position}%")
                else:
                    self.call_service("cover/close_cover", entity_id=zone.damper_entity)
                    self.log(f"Closed {zone_name} damper")
                    
            except Exception as e:
                self.log(f"Error setting damper for {zone_name}: {e}", level="ERROR")

    def _set_hvac_mode(self, mode: HVACMode):
        """Set the main HVAC system mode"""
        try:
            current_mode = self.get_state(self.config.main_climate)
            if current_mode != mode.value:
                self.call_service(
                    "climate/set_hvac_mode",
                    entity_id=self.config.main_climate,
                    hvac_mode=mode.value
                )
                self.current_hvac_mode = mode.value
                self.log(f"Set HVAC mode to {mode.value}")
        except Exception as e:
            self.log(f"Error setting HVAC mode: {e}", level="ERROR")

    def _all_zones_satisfied(self) -> bool:
        """Check if all active zones are within their target temperature range"""
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue
                
            temp_min = zone.target_temp
            temp_max = zone.target_temp + self.config.temp_tolerance
            
            if not (temp_min <= zone.current_temp <= temp_max):
                return False
                
        return True

    def _deactivate_algorithm(self):
        """Deactivate the smart algorithm and return to idle mode"""
        self.log("All zones satisfied, deactivating algorithm")
        
        # Set HVAC to idle mode
        self._set_hvac_mode(HVACMode.DRY)
        
        # Close all dampers gradually (let Airtouch handle it)
        # We don't force close dampers to let the normal system take over
        
        self.algorithm_active = False

    def toggle_controller(self, state: bool):
        """Enable or disable the smart controller"""
        self.config.enabled = state
        self.log(f"Smart controller {'enabled' if state else 'disabled'}")
        
        if not state and self.algorithm_active:
            self._deactivate_algorithm()

    def get_status(self) -> Dict:
        """Get current status of the controller"""
        active_zones = [name for name, zone in self.zones.items() if zone.is_active]
        
        return {
            "enabled": self.config.enabled,
            "algorithm_active": self.algorithm_active,
            "current_hvac_mode": self.current_hvac_mode,
            "active_zones": active_zones,
            "last_check": self.last_check_time.isoformat() if self.last_check_time else None,
            "zone_states": {
                name: {
                    "current_temp": zone.current_temp,
                    "target_temp": zone.target_temp,
                    "is_active": zone.is_active,
                    "damper_position": zone.damper_position
                }
                for name, zone in self.zones.items()
            }
        } 