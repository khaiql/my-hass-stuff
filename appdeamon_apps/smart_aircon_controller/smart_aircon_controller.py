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
        self.algorithm_mode: Optional[HVACMode] = None
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
        
        # Schedule entity validation after Home Assistant has time to fully load
        self.run_in(self._validate_entities, 30)
        
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
                # Get required entities
                climate_entity = zone_config["climate_entity"]
                damper_entity = zone_config["damper_entity"]
                
                # Check entities exist, but don't skip zones during startup
                # Entity checks during startup can be unreliable
                climate_exists = self._entity_exists(climate_entity)
                damper_exists = self._entity_exists(damper_entity)
                
                if not climate_exists:
                    self.log(f"Warning: Climate entity {climate_entity} not found during startup - will retry later", level="WARNING")
                    
                if not damper_exists:
                    self.log(f"Warning: Damper entity {damper_entity} not found during startup - will retry later", level="WARNING")
                
                # Create zone state even if entities aren't found yet
                # They may become available after Home Assistant fully loads
                zone_state = ZoneState(
                    entity_id=climate_entity,
                    damper_entity=damper_entity,
                    current_temp=0.0,
                    target_temp=0.0,
                    is_active=False,
                    isolation=zone_config.get("isolation", False)
                )
                
                self.zones[zone_name] = zone_state
                self.log(f"Initialized zone: {zone_name} (entities available: climate={climate_exists}, damper={damper_exists})")
                
            except KeyError as e:
                self.log(f"Error initializing zone {zone_name}: Missing config {e}", level="ERROR")
            except Exception as e:
                self.log(f"Error initializing zone {zone_name}: {e}", level="ERROR")

    def _entity_exists(self, entity_id: str) -> bool:
        """Check if an entity exists in Home Assistant"""
        try:
            state = self.get_state(entity_id)
            # Entity exists if state is not None and not "unavailable"
            # During startup, entities might be "unavailable" temporarily
            return state is not None and state != "unavailable"
        except Exception as e:
            self.log(f"Error checking entity {entity_id}: {e}", level="DEBUG")
            return False

    def _validate_entities(self, kwargs):
        """Validate all entities after Home Assistant has fully loaded"""
        self.log("Validating entities after startup...")
        
        # Check main climate entity
        if not self._entity_exists(self.config.main_climate):
            self.log(f"ERROR: Main climate entity {self.config.main_climate} not found!", level="ERROR")
        else:
            self.log(f"Main climate entity {self.config.main_climate} validated")
        
        # Check all zone entities
        missing_entities = []
        for zone_name, zone in self.zones.items():
            climate_exists = self._entity_exists(zone.entity_id)
            damper_exists = self._entity_exists(zone.damper_entity)
            
            if not climate_exists:
                missing_entities.append(f"{zone_name}: {zone.entity_id}")
            if not damper_exists:
                missing_entities.append(f"{zone_name}: {zone.damper_entity}")
                
            if climate_exists and damper_exists:
                self.log(f"Zone {zone_name}: All entities validated")
            else:
                self.log(f"Zone {zone_name}: Missing entities - climate={climate_exists}, damper={damper_exists}", level="WARNING")
        
        if missing_entities:
            self.log(f"The following entities are still missing after startup: {missing_entities}", level="ERROR")
            self.log("Please check your Home Assistant configuration and entity names", level="ERROR")
        else:
            self.log("All entities validated successfully!")

    def _periodic_check(self, kwargs):
        """Periodic check function called every check_interval seconds"""
        if not self.config.enabled:
            return
            
        try:
            self.last_check_time = datetime.datetime.now()
            self._update_zone_states()
            
            zones_needing_heating, zones_needing_cooling = self._analyze_zones()

            # If algorithm is already running, it must complete its cycle before switching.
            if self.algorithm_active:
                if self._all_zones_satisfied():
                    self.log("Current cycle complete.")
                    self._deactivate_algorithm()
                # If cycle isn't complete, we might re-evaluate dampers, but we don't switch modes.
                # The _execute call will recalculate and apply damper positions.
                elif self.algorithm_mode == HVACMode.HEAT and zones_needing_heating:
                    self.log("Heating cycle continues. Re-evaluating damper positions.")
                    self._execute_smart_algorithm(zones_needing_heating, HVACMode.HEAT)
                elif self.algorithm_mode == HVACMode.COOL and zones_needing_cooling:
                    self.log("Cooling cycle continues. Re-evaluating damper positions.")
                    self._execute_smart_algorithm(zones_needing_cooling, HVACMode.COOL)
                return

            # If algorithm is NOT active, decide which mode to start, if any.
            if zones_needing_heating:
                if zones_needing_cooling:
                    self.log("Conflict: Zones need both heating and cooling. Prioritizing heating.", level="WARNING")
                self._execute_smart_algorithm(zones_needing_heating, HVACMode.HEAT)
            elif zones_needing_cooling:
                self._execute_smart_algorithm(zones_needing_cooling, HVACMode.COOL)
                    
        except Exception as e:
            self.log(f"Error in periodic check: {e}", level="ERROR")

    def _update_zone_states(self):
        """Update current state of all zones"""
        for zone_name, zone in self.zones.items():
            try:
                # Get climate entity state and attributes
                climate_full_state = self.get_state(zone.entity_id, attribute="all")
                
                if not climate_full_state or "state" not in climate_full_state or climate_full_state["state"] in ["unavailable", "unknown", None]:
                    continue
                
                # Update zone state from attributes
                climate_state = climate_full_state["state"]
                attributes = climate_full_state.get("attributes", {})
                
                zone.is_active = climate_state not in ["off", "unavailable"]
                zone.target_temp = float(attributes.get("temperature", 0.0))
                zone.current_temp = float(attributes.get("current_temperature", 0.0))
                
                # Get damper position
                damper_state = self.get_state(zone.damper_entity, attribute="current_position")
                if damper_state is not None:
                    zone.damper_position = int(damper_state)
                    
            except (ValueError, TypeError) as e:
                self.log(f"Error processing state for zone {zone_name}: {e}", level="WARNING")
            except Exception as e:
                self.log(f"Error updating zone {zone_name}: {e}", level="ERROR")

    def _analyze_zones(self) -> Tuple[List[str], List[str]]:
        """Analyze zones to determine which need heating/cooling"""
        zones_needing_heating = []
        zones_needing_cooling = []
        
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue
                
            # Check if zone needs heating
            if zone.current_temp < (zone.target_temp - self.config.temp_tolerance):
                zones_needing_heating.append(zone_name)
                self.log(f"Zone {zone_name} needs heating: {zone.current_temp}°C < {zone.target_temp - self.config.temp_tolerance}°C")
            
            # Check if zone needs cooling
            elif zone.current_temp > (zone.target_temp + self.config.temp_tolerance):
                zones_needing_cooling.append(zone_name)
                self.log(f"Zone {zone_name} needs cooling: {zone.current_temp}°C > {zone.target_temp + self.config.temp_tolerance}°C")
                
        return zones_needing_heating, zones_needing_cooling

    def _execute_smart_algorithm(self, trigger_zones: List[str], mode: HVACMode):
        """Execute the smart heating/cooling algorithm"""
        self.log(f"Executing smart {mode.value} algorithm for zones: {trigger_zones}")
        
        # Calculate damper positions for all active zones
        damper_positions = self._calculate_damper_positions(trigger_zones, mode)
        
        # Set HVAC to the appropriate mode
        self._set_hvac_mode(mode)
        
        # Apply damper positions
        self._apply_damper_positions(damper_positions)
        
        self.algorithm_active = True
        self.algorithm_mode = mode

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
        if not self.algorithm_mode:
            return True # Should not happen if algorithm is active

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
        
        # Close all dampers gradually (let Airtouch handle it)
        # We don't force close dampers to let the normal system take over
        
        self.algorithm_active = False
        self.algorithm_mode = None

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
            "algorithm_mode": self.algorithm_mode.value if self.algorithm_mode else None,
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