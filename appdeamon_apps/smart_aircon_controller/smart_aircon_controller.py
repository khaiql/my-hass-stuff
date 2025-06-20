import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import appdaemon.plugins.hass.hassapi as hass


class HVACMode(Enum):
    """HVAC operating modes."""

    HEAT = "heat"
    COOL = "cool"
    DRY = "dry"
    FAN = "fan"
    OFF = "off"


@dataclass
class ZoneState:
    """State of a single zone."""

    entity_id: str
    damper_entity: str
    current_temp: float
    target_temp: float
    is_active: bool
    isolation: bool = False
    damper_position: int = 0


@dataclass
class ControllerConfig:
    """Configuration for the smart aircon controller."""

    # Static configuration (requires restart)
    check_interval: int = 30
    main_climate: str = "climate.aircon"
    algorithm_timeout_minutes: int = 30
    stability_check_minutes: int = 10
    progress_timeout_minutes: int = 15

    # Dynamic configuration (runtime changeable via HA entities)
    enabled: bool = True
    temp_tolerance: float = 0.5
    smart_hvac_mode: str = "heat"  # "heat" or "cool"
    primary_damper_percent: int = 50
    secondary_damper_percent: int = 40
    overflow_damper_percent: int = 10
    minimum_damper_percent: int = 5


class ConfigManager:
    """Manages dynamic configuration from Home Assistant entities."""

    def __init__(
        self, hass_api, config_entities: Dict[str, str], defaults: Dict[str, Any]
    ):
        self.hass = hass_api
        self.config_entities = config_entities
        self.defaults = defaults
        self.current_config = ControllerConfig()
        self.last_update = None

        # Load initial configuration
        self.update_config()

    def update_config(self) -> bool:
        """Update configuration from HA entities. Returns True if any values changed."""
        changed = False
        new_values = {}

        # Read each config entity
        for config_key, entity_id in self.config_entities.items():
            try:
                entity = self.hass.get_entity(entity_id)
                state = entity.get_state()

                if state in ["unavailable", "unknown", None]:
                    # Use fallback value
                    value = self.defaults.get(config_key)
                    self.hass.log(
                        f"WARNING: Config entity {entity_id} unavailable, using default: {value}"
                    )
                else:
                    # Convert state to appropriate type
                    if config_key == "enabled":
                        value = state.lower() in ["on", "true", "1"]
                    elif config_key == "smart_hvac_mode":
                        value = str(state).lower()
                    else:
                        # Numeric values
                        value = (
                            float(state)
                            if config_key == "temp_tolerance"
                            else int(float(state))
                        )

                        # Validate ranges
                        value = self._validate_numeric_value(config_key, value)

                new_values[config_key] = value

                # Check if value changed
                if getattr(self.current_config, config_key) != value:
                    self.hass.log(
                        f"Config changed: {config_key} = {value} (was {getattr(self.current_config, config_key)})"
                    )
                    changed = True

            except Exception as e:
                # Use fallback value on error
                value = self.defaults.get(config_key)
                new_values[config_key] = value
                self.hass.log(
                    f"Error reading config entity {entity_id}: {e}, using default: {value}"
                )

        # Update config object
        for key, value in new_values.items():
            setattr(self.current_config, key, value)

        self.last_update = datetime.datetime.now()
        return changed

    def _validate_numeric_value(self, config_key: str, value: float) -> float:
        """Validate numeric configuration values and clamp to safe ranges."""
        ranges = {
            "temp_tolerance": (0.1, 5.0),
            "primary_damper_percent": (30, 100),
            "secondary_damper_percent": (20, 80),
            "overflow_damper_percent": (5, 50),
            "minimum_damper_percent": (1, 20),
        }

        if config_key in ranges:
            min_val, max_val = ranges[config_key]
            if value < min_val:
                self.hass.log(
                    f"WARNING: {config_key} value {value} below minimum {min_val}, clamping"
                )
                return min_val
            elif value > max_val:
                self.hass.log(
                    f"WARNING: {config_key} value {value} above maximum {max_val}, clamping"
                )
                return max_val

        return value

    def get_config(self) -> ControllerConfig:
        """Get current configuration."""
        return self.current_config

    def should_update(self) -> bool:
        """Check if config should be updated (every 60 seconds)."""
        if not self.last_update:
            return True

        return (datetime.datetime.now() - self.last_update).total_seconds() >= 60


class StateManager:
    """Manages all zone states and HVAC state."""

    def __init__(
        self, hass_api, config: ControllerConfig, zones_config: Dict[str, Dict]
    ):
        self.hass = hass_api
        self.config = config
        self.zones: Dict[str, ZoneState] = {}
        self.current_hvac_mode: Optional[str] = None
        self.temperature_history: Dict[str, List[Tuple[datetime.datetime, float]]] = {}
        self.controller_ref = None  # Will be set by controller

        self._initialize_zones(zones_config)

    def _initialize_zones(self, zones_config: Dict[str, Dict]):
        """Initialize zone configurations."""
        for zone_name, zone_config in zones_config.items():
            try:
                climate_entity = zone_config["climate_entity"]
                damper_entity = zone_config["damper_entity"]
                isolation = zone_config.get("isolation", False)

                zone_state = ZoneState(
                    entity_id=climate_entity,
                    damper_entity=damper_entity,
                    current_temp=0.0,
                    target_temp=0.0,
                    is_active=False,
                    isolation=isolation,
                )

                self.zones[zone_name] = zone_state
                self.temperature_history[zone_name] = []

            except KeyError as e:
                self.hass.log(
                    f"Error initializing zone {zone_name}: Missing config {e}"
                )
            except Exception as e:
                self.hass.log(f"Error initializing zone {zone_name}: {e}")

    def update_all_zones(self):
        """Update state for all zones from Home Assistant entities."""
        for zone_name, zone in self.zones.items():
            try:
                self._update_single_zone(zone_name, zone)
            except Exception as e:
                self.hass.log(f"Error updating zone {zone_name}: {e}")

    def _update_single_zone(self, zone_name: str, zone: ZoneState):
        """Update state for a single zone."""
        try:
            # Update climate entity state
            climate_entity = self.hass.get_entity(zone.entity_id)
            climate_state = climate_entity.get_state()

            if climate_state not in ["unavailable", "unknown", None]:
                zone.is_active = climate_state not in [
                    "off",
                    "unavailable",
                    "unknown",
                    None,
                ]

                # Get temperature values
                target_temp = climate_entity.attributes.get("temperature", 0.0)
                current_temp = climate_entity.attributes.get("current_temperature", 0.0)

                raw_target_temp = float(target_temp) if target_temp is not None else 0.0
                zone.current_temp = (
                    float(current_temp) if current_temp is not None else 0.0
                )
                
                # Use effective target temp (stored sensor value if in idle mode)
                if self.controller_ref:
                    zone.target_temp = self.controller_ref._get_effective_target_temp(
                        zone_name, raw_target_temp
                    )
                else:
                    zone.target_temp = raw_target_temp

            # Update damper position
            damper_entity = self.hass.get_entity(zone.damper_entity)
            damper_position = damper_entity.attributes.get("current_position", 0)
            zone.damper_position = (
                int(damper_position) if damper_position is not None else 0
            )

            # Update temperature history
            self._update_temperature_history(zone_name, zone.current_temp)

        except Exception as e:
            self.hass.log(f"Error updating single zone {zone_name}: {e}")

    def _update_temperature_history(self, zone_name: str, current_temp: float):
        """Update temperature history for a zone."""
        now = datetime.datetime.now()

        # Add current reading
        self.temperature_history[zone_name].append((now, current_temp))

        # Keep only last 30 minutes of data
        cutoff_time = now - datetime.timedelta(minutes=30)
        self.temperature_history[zone_name] = [
            (time, temp)
            for time, temp in self.temperature_history[zone_name]
            if time > cutoff_time
        ]

    def update_hvac_mode(self):
        """Update current HVAC mode from main climate entity."""
        try:
            main_entity = self.hass.get_entity(self.config.main_climate)
            self.current_hvac_mode = main_entity.get_state()
        except Exception as e:
            self.hass.log(f"Error getting HVAC mode: {e}")
            self.current_hvac_mode = "unknown"

    def get_active_zones(self) -> List[str]:
        """Get list of active zone names."""
        return [name for name, zone in self.zones.items() if zone.is_active]

    def get_zones_needing_heating(self) -> List[str]:
        """Get zones that need heating (temp < target - tolerance)."""
        if self.config.smart_hvac_mode != "heat":
            return []

        zones_needing_heat = []
        threshold_temp = lambda target: target - self.config.temp_tolerance

        for zone_name, zone in self.zones.items():
            if zone.is_active and zone.current_temp < threshold_temp(zone.target_temp):
                zones_needing_heat.append(zone_name)

        return zones_needing_heat

    def get_zones_needing_cooling(self) -> List[str]:
        if self.config.smart_hvac_mode != "cool":
            return []
        """Get zones that need cooling (temp > target + tolerance)."""
        zones_needing_cool = []
        threshold_temp = lambda target: target + self.config.temp_tolerance

        for zone_name, zone in self.zones.items():
            if zone.is_active and zone.current_temp > threshold_temp(zone.target_temp):
                zones_needing_cool.append(zone_name)

        return zones_needing_cool

    def all_zones_satisfied(self, mode: HVACMode) -> bool:
        """Check if all active zones are satisfied for the given mode."""
        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue

            if mode == HVACMode.HEAT:
                # Satisfied if temp > target (exceeded target)
                if zone.current_temp <= zone.target_temp:
                    return False
            elif mode == HVACMode.COOL:
                # Satisfied if temp < target (cooled below target)
                if zone.current_temp >= zone.target_temp:
                    return False

        return True

    def all_dampers_low(self, threshold: int = 10) -> bool:
        """Check if all active zone dampers are below threshold."""
        active_zones = [zone for zone in self.zones.values() if zone.is_active]
        if not active_zones:
            return True

        return all(zone.damper_position <= threshold for zone in active_zones)

    def is_temperature_stable(
        self, zone_name: str, minutes: int = 5, threshold: float = 0.1
    ) -> bool:
        """Check if zone temperature has been stable for given time."""
        if zone_name not in self.temperature_history:
            return False

        now = datetime.datetime.now()
        check_time = now - datetime.timedelta(minutes=minutes)

        # Get readings from the stability check period
        stable_readings = [
            temp
            for time, temp in self.temperature_history[zone_name]
            if time >= check_time
        ]

        if len(stable_readings) < 3:  # Need enough data points
            return False

        # Check if temperature has been stable within threshold
        min_temp = min(stable_readings)
        max_temp = max(stable_readings)
        return max_temp - min_temp <= threshold

    def get_zone_state(self, zone_name: str) -> Optional[ZoneState]:
        """Get state for a specific zone."""
        return self.zones.get(zone_name)

    def get_all_zone_states(self) -> Dict[str, ZoneState]:
        """Get all zone states."""
        return self.zones.copy()

    def is_zone_isolated(self, zone_name: str) -> bool:
        """Check if zone is isolated."""
        zone = self.zones.get(zone_name)
        return zone.isolation if zone else False

    def get_time_since_last_hvac_mode_change(self) -> Optional[datetime.datetime]:
        """Get the time of the last HVAC mode change from Home Assistant history."""
        try:
            # Get history for the main climate entity for the last 24 hours
            history = self.hass.get_history(
                entity_id=self.config.main_climate,
                days=1
            )
            
            if not history or not history[0]:
                return None
            
            # Find the most recent state change
            entity_history = history[0]
            if len(entity_history) < 2:
                # No state changes in the last 24 hours
                return None
            
            # Get the most recent state change (excluding the current state)
            # The last entry is the current state, so we want the second to last
            if len(entity_history) >= 2:
                last_change = entity_history[-2]
                last_changed_str = last_change.get('last_changed')
                if last_changed_str:
                    # Convert ISO 8601 string to datetime object
                    return self.hass.convert_utc(last_changed_str)
            
            return None
            
        except Exception as e:
            self.hass.log(f"Error getting HVAC mode change history: {e}")
            return None


class DecisionEngine:
    """Makes all control decisions based on current state."""

    def __init__(self, config: ControllerConfig):
        self.config = config

    def get_idle_mode(self, smart_hvac_mode: str) -> HVACMode:
        """Get appropriate idle mode based on smart HVAC mode"""
        if smart_hvac_mode == "heat":
            return HVACMode.DRY
        elif smart_hvac_mode == "cool":
            return HVACMode.FAN
        else:
            return HVACMode.DRY  # Default fallback

    def should_activate_heating(self, state_manager: StateManager) -> bool:
        """Determine if heating should be activated."""
        if self.config.smart_hvac_mode != "heat":
            return False

        zones_needing_heat = state_manager.get_zones_needing_heating()
        return len(zones_needing_heat) > 0

    def should_activate_cooling(self, state_manager: StateManager) -> bool:
        """Determine if cooling should be activated."""
        if self.config.smart_hvac_mode != "cool":
            return False

        zones_needing_cool = state_manager.get_zones_needing_cooling()
        return len(zones_needing_cool) > 0

    def should_switch_to_idle(
        self, state_manager: StateManager, current_mode: HVACMode
    ) -> bool:
        """Determine if system should switch to idle mode."""
        # Check if enough time has passed since last HVAC mode change
        last_change_time = state_manager.get_time_since_last_hvac_mode_change()
        if last_change_time is not None:
            import datetime
            now = datetime.datetime.now()
            time_diff = now - last_change_time
            stability_threshold = datetime.timedelta(minutes=self.config.stability_check_minutes)
            
            if time_diff < stability_threshold:
                return False  # Not enough time has passed
        
        if current_mode == HVACMode.HEAT:
            # Switch to DRY if all zones satisfied and dampers are low
            return (
                state_manager.all_zones_satisfied(HVACMode.HEAT)
                and state_manager.all_dampers_low()
            )
        elif current_mode == HVACMode.COOL:
            # Switch to FAN if all zones satisfied and dampers are low
            return (
                state_manager.all_zones_satisfied(HVACMode.COOL)
                and state_manager.all_dampers_low()
            )

        return False

    def get_target_hvac_mode(self, state_manager: StateManager) -> HVACMode:
        """Get the target HVAC mode based on current state."""
        if self.config.smart_hvac_mode == "heat":
            if self.should_activate_heating(state_manager):
                return HVACMode.HEAT
            else:
                return self.get_idle_mode("heat")
        elif self.config.smart_hvac_mode == "cool":
            if self.should_activate_cooling(state_manager):
                return HVACMode.COOL
            else:
                return self.get_idle_mode("cool")

        return self.get_idle_mode("heat")  # Default fallback

    def calculate_damper_positions(
        self, state_manager: StateManager, trigger_zones: List[str], mode: HVACMode
    ) -> Dict[str, int]:
        """Calculate optimal damper positions for all zones."""
        damper_positions = {}

        for zone_name, zone in state_manager.get_all_zone_states().items():
            if not zone.is_active:
                damper_positions[zone_name] = 0
                continue

            # Always maintain minimum damper for active zones
            min_damper = self.config.minimum_damper_percent

            if zone.isolation and zone_name not in trigger_zones:
                # Isolated zones only get minimum unless they triggered
                damper_positions[zone_name] = min_damper
                continue

            if zone_name in trigger_zones:
                # Primary trigger zone gets full opening
                damper_positions[zone_name] = self.config.primary_damper_percent
            else:
                # Calculate secondary zone damper based on need
                damper_positions[zone_name] = self._calculate_secondary_damper(
                    zone, mode, min_damper
                )

        return damper_positions

    def _calculate_secondary_damper(
        self, zone: ZoneState, mode: HVACMode, min_damper: int
    ) -> int:
        """Calculate damper position for secondary zones."""
        if mode == HVACMode.HEAT:
            max_desired_temp = zone.target_temp + self.config.temp_tolerance

            if zone.current_temp < max_desired_temp:
                if zone.current_temp < zone.target_temp:
                    # Zone below target - secondary damper
                    return self.config.secondary_damper_percent
                else:
                    # Zone above target but below max - overflow damper
                    return self.config.overflow_damper_percent
            else:
                # Zone at or above max - minimum damper
                return min_damper

        elif mode == HVACMode.COOL:
            min_desired_temp = zone.target_temp - self.config.temp_tolerance

            if zone.current_temp > min_desired_temp:
                if zone.current_temp > zone.target_temp:
                    # Zone above target - secondary damper
                    return self.config.secondary_damper_percent
                else:
                    # Zone below target but above min - overflow damper
                    return self.config.overflow_damper_percent
            else:
                # Zone at or below min - minimum damper
                return min_damper

        return min_damper


class Executor:
    """Executes decisions via Home Assistant API calls."""

    def __init__(self, hass_api, config: ControllerConfig):
        self.hass = hass_api
        self.config = config

    def set_hvac_mode(self, mode: HVACMode):
        """Set the main HVAC system mode."""
        try:
            self.hass.call_service(
                "climate/set_hvac_mode",
                entity_id=self.config.main_climate,
                hvac_mode=mode.value,
            )
            self.hass.log(f"Set HVAC mode to {mode.value}")
        except Exception as e:
            self.hass.log(f"Error setting HVAC mode to {mode.value}: {e}")

    def set_damper_positions(
        self, positions: Dict[str, int], state_manager: StateManager
    ):
        """Set damper positions for all zones."""
        for zone_name, position in positions.items():
            zone = state_manager.get_zone_state(zone_name)
            if not zone:
                continue

            try:
                self.hass.call_service(
                    "cover/set_cover_position",
                    entity_id=zone.damper_entity,
                    position=position,
                )
                self.hass.log(f"Set {zone_name} damper to {position}%")
            except Exception as e:
                self.hass.log(f"Error setting damper for {zone_name}: {e}")

    def set_minimum_dampers(self, state_manager: StateManager):
        """Set all active zone dampers to minimum position."""
        positions = {}
        for zone_name, zone in state_manager.get_all_zone_states().items():
            if zone.is_active:
                positions[zone_name] = self.config.minimum_damper_percent

        self.set_damper_positions(positions, state_manager)


class Monitor:
    """Monitors system health and implements fallback logic."""

    def __init__(self, config: ControllerConfig):
        self.config = config
        self.algorithm_start_time: Optional[datetime.datetime] = None
        self.last_progress_time: Optional[datetime.datetime] = None

    def start_monitoring(self):
        """Start monitoring algorithm execution."""
        self.algorithm_start_time = datetime.datetime.now()
        self.last_progress_time = datetime.datetime.now()

    def stop_monitoring(self):
        """Stop monitoring and reset timers."""
        self.algorithm_start_time = None
        self.last_progress_time = None

    def check_progress(self, state_manager: StateManager, mode: HVACMode) -> bool:
        """Check if algorithm is making progress."""
        if not self.algorithm_start_time:
            return True

        now = datetime.datetime.now()

        # Check for any temperature progress in the last 5 minutes
        for zone_name, zone in state_manager.get_all_zone_states().items():
            if not zone.is_active:
                continue

            if self._zone_making_progress(state_manager, zone_name, mode, now):
                self.last_progress_time = now
                return True

        return True  # Assume progress if we can't determine otherwise

    def _zone_making_progress(
        self,
        state_manager: StateManager,
        zone_name: str,
        mode: HVACMode,
        now: datetime.datetime,
    ) -> bool:
        """Check if a specific zone is making temperature progress."""
        if zone_name not in state_manager.temperature_history:
            return False

        # Get temperature from 5 minutes ago
        five_min_ago = now - datetime.timedelta(minutes=5)
        old_readings = [
            (time, temp)
            for time, temp in state_manager.temperature_history[zone_name]
            if time <= five_min_ago
        ]

        if not old_readings:
            return False

        old_temp = old_readings[-1][1]  # Most recent old reading
        current_temp = state_manager.get_zone_state(zone_name).current_temp
        progress_threshold = 0.1  # 0.1°C progress threshold

        if mode == HVACMode.HEAT:
            return current_temp > old_temp + progress_threshold
        elif mode == HVACMode.COOL:
            return current_temp < old_temp - progress_threshold

        return False

    def should_fallback(self, state_manager: StateManager) -> bool:
        """Check if fallback mechanisms should be triggered."""
        if not self.algorithm_start_time:
            return False

        now = datetime.datetime.now()
        runtime = now - self.algorithm_start_time

        # Fallback 1: Maximum timeout reached
        if runtime.total_seconds() >= self.config.algorithm_timeout_minutes * 60:
            return True

        # Fallback 2: No progress for extended time
        if self.last_progress_time:
            time_since_progress = now - self.last_progress_time
            if (
                time_since_progress.total_seconds()
                >= self.config.progress_timeout_minutes * 60
            ):
                return True

        return False


class SmartAirconController(hass.Hass):
    """
    Smart Aircon Controller V2 - Simplified Implementation

    Main controller that orchestrates all components for energy-efficient
    heating/cooling with clean separation of concerns.
    """

    def initialize(self):
        """Initialize the smart aircon controller."""
        self.log("Initializing Smart Aircon Controller V2")

        # Load static configuration
        self.static_config = self._load_static_config()

        # Initialize dynamic configuration manager
        config_entities = self.args.get("config_entities", {})
        config_defaults = self.args.get("config_defaults", {})

        if not config_entities:
            raise ValueError(
                "config_entities is required. Please see home_assistant_config.yaml for required helper entities."
            )

        self.log("Using dynamic configuration from Home Assistant entities")
        self.config_manager = ConfigManager(self, config_entities, config_defaults)

        # Initialize components
        config = self.config_manager.get_config()
        self.state_manager = StateManager(self, config, self.args.get("zones", {}))
        self.state_manager.controller_ref = self  # Set reference for effective target temp
        self.decision_engine = DecisionEngine(config)
        self.executor = Executor(self, config)
        self.monitor = Monitor(config)

        # Algorithm state
        self.algorithm_active = False
        self.current_algorithm_mode: Optional[HVACMode] = None
        self._pending_activation_mode: Optional[HVACMode] = None

        # Set up periodic checking
        self.run_every(
            self._periodic_check,
            "now+10",
            self.static_config.check_interval,
        )
        self.log(
            f"Controller initialized - checking every {self.static_config.check_interval} seconds"
        )

        # Validate entities after startup
        self.run_in(self._validate_entities, 30)

    def _load_static_config(self) -> ControllerConfig:
        """Load static configuration that requires restart to change."""
        return ControllerConfig(
            check_interval=self.args.get("check_interval", 30),
            main_climate=self.args.get("main_climate", "climate.aircon"),
            algorithm_timeout_minutes=self.args.get("algorithm_timeout_minutes", 30),
            stability_check_minutes=self.args.get("stability_check_minutes", 10),
            progress_timeout_minutes=self.args.get("progress_timeout_minutes", 15),
        )

    def _validate_entities(self, kwargs):
        """Validate all entities after Home Assistant has fully loaded."""
        self.log("Validating entities...")

        # Check main climate entity
        try:
            main_entity = self.get_entity(self.static_config.main_climate)
            if main_entity.get_state() in ["unavailable", "unknown", None]:
                self.log(
                    f"WARNING: Main climate entity {self.static_config.main_climate} not available"
                )
            else:
                self.log("Main climate entity validated")
        except Exception as e:
            self.log(f"ERROR: Main climate entity validation failed: {e}")

        # Check zone entities
        missing_entities = []
        for zone_name, zone in self.state_manager.zones.items():
            try:
                climate_entity = self.get_entity(zone.entity_id)
                damper_entity = self.get_entity(zone.damper_entity)

                if climate_entity.get_state() in ["unavailable", "unknown", None]:
                    missing_entities.append(f"{zone_name} climate: {zone.entity_id}")

                if damper_entity.get_state() in ["unavailable", "unknown", None]:
                    missing_entities.append(f"{zone_name} damper: {zone.damper_entity}")

            except Exception as e:
                missing_entities.append(f"{zone_name}: {e}")

        if missing_entities:
            self.log(f"WARNING: Missing entities: {missing_entities}")
        else:
            self.log("All entities validated successfully")

    def _periodic_check(self, kwargs):
        """Periodic check function called every check_interval seconds."""
        try:
            self.log("=== PERIODIC CHECK START ===")

            # Update dynamic configuration
            if self.config_manager.should_update():
                self.log("Updating dynamic configuration from HA entities")
                config_changed = self.config_manager.update_config()
                if config_changed:
                    self.log("Configuration changed, updating components")
                    # Update components with new config
                    current_config = self.config_manager.get_config()
                    self.decision_engine.config = current_config
                    self.state_manager.config = current_config
                    self.executor.config = current_config
                    self.monitor.config = current_config
            current_config = self.config_manager.get_config()

            self.log(
                f"Controller enabled: {current_config.enabled}, Smart HVAC mode: {current_config.smart_hvac_mode}"
            )

            # Check if controller is enabled
            if not current_config.enabled:
                self.log("Controller is disabled")
                if self.algorithm_active:
                    self.log("Controller disabled, deactivating algorithm")
                    self._deactivate_algorithm()
                else:
                    self.log("Algorithm already inactive")
                return

            # Update all state
            self.log("Updating zone states and HVAC mode")
            self.state_manager.update_all_zones()
            self.state_manager.update_hvac_mode()

            # Log current state
            active_zones = self.state_manager.get_active_zones()
            self.log(f"Current HVAC mode: {self.state_manager.current_hvac_mode}")
            self.log(f"Active zones: {active_zones}")

            # Log zone details
            for zone_name, zone in self.state_manager.zones.items():
                if zone.is_active:
                    self.log(
                        f"Zone {zone_name}: {zone.current_temp}°C -> {zone.target_temp}°C (damper: {zone.damper_position}%)"
                    )

            # Check zone needs
            zones_needing_heat = self.state_manager.get_zones_needing_heating()
            zones_needing_cool = self.state_manager.get_zones_needing_cooling()
            self.log(f"Zones needing heat: {zones_needing_heat}")
            self.log(f"Zones needing cool: {zones_needing_cool}")

            # Get target mode from decision engine
            target_mode = self.decision_engine.get_target_hvac_mode(self.state_manager)
            self.log(f"Target HVAC mode: {target_mode.value}")
            self.log(
                f"Algorithm active: {self.algorithm_active}, Current algorithm mode: {self.current_algorithm_mode.value if self.current_algorithm_mode else 'None'}"
            )

            # Check if we need to activate algorithm or switch to idle
            if not self.algorithm_active:
                self.log("Algorithm is inactive, checking if activation needed")
                if self._should_activate_algorithm(target_mode):
                    self.log(
                        f"Algorithm activation triggered for {target_mode.value} mode"
                    )
                    self._activate_algorithm(target_mode)
                elif self._should_switch_to_idle_mode(target_mode):
                    self.log(f"Switching to idle mode: {target_mode.value}")
                    self._switch_to_idle_mode(target_mode)
                else:
                    self.log("No algorithm activation or mode change needed")
            else:
                self.log("Algorithm is active, checking if deactivation needed")
                # Algorithm is active - check if we should deactivate
                if self._should_deactivate_algorithm(target_mode):
                    self.log("Algorithm deactivation triggered")
                    self._deactivate_algorithm()
                else:
                    self.log("Algorithm continues running, checking progress")
                    # Continue monitoring
                    progress_ok = self.monitor.check_progress(
                        self.state_manager, self.current_algorithm_mode
                    )
                    self.log(f"Progress check result: {progress_ok}")

                    if self.monitor.should_fallback(self.state_manager):
                        self.log("Fallback triggered - deactivating algorithm")
                        self._deactivate_algorithm()
                    else:
                        self.log("Algorithm monitoring continues")

            self.log("=== PERIODIC CHECK END ===")

        except Exception as e:
            self.log(f"Error in periodic check: {e}")

    def _should_activate_algorithm(self, target_mode: HVACMode) -> bool:
        """Determine if algorithm should be activated."""
        current_mode = self.state_manager.current_hvac_mode
        self.log(
            f"Checking activation: target={target_mode.value}, current={current_mode}"
        )

        # Check if enough time has passed since last HVAC mode change
        last_change_time = self.state_manager.get_time_since_last_hvac_mode_change()
        if last_change_time is not None:
            import datetime
            now = datetime.datetime.now()
            time_diff = now - last_change_time
            stability_threshold = datetime.timedelta(minutes=self.static_config.stability_check_minutes)
            
            if time_diff < stability_threshold:
                self.log(f"Stability check: Not enough time passed since last HVAC change ({time_diff} < {stability_threshold})")
                return False

        # Activate if target mode requires heating/cooling and current mode is idle
        if target_mode in [HVACMode.HEAT, HVACMode.COOL]:
            if (
                current_mode in ["dry", "fan", "off"]
                or current_mode != target_mode.value
            ):
                self.log(
                    f"Activation needed: target mode {target_mode.value} requires active heating/cooling"
                )
                return True
            else:
                self.log(f"No activation needed: already in {target_mode.value} mode")
        else:
            self.log(
                f"No activation needed: target mode {target_mode.value} is idle mode"
            )

        return False

    def _should_deactivate_algorithm(self, target_mode: HVACMode) -> bool:
        """Determine if algorithm should be deactivated."""
        self.log(
            f"Checking deactivation: target={target_mode.value}, current_algorithm={self.current_algorithm_mode.value if self.current_algorithm_mode else 'None'}"
        )

        # Deactivate if target mode is idle (DRY/FAN)
        if target_mode in [HVACMode.DRY, HVACMode.FAN]:
            should_switch = self.decision_engine.should_switch_to_idle(
                self.state_manager, self.current_algorithm_mode
            )
            self.log(f"Target is idle mode, should_switch_to_idle: {should_switch}")
            return should_switch
        else:
            self.log(f"Target mode {target_mode.value} is active mode, no deactivation")

        return False

    def _should_switch_to_idle_mode(self, target_mode: HVACMode) -> bool:
        """Determine if we should switch to idle mode when algorithm is inactive."""
        current_mode = self.state_manager.current_hvac_mode

        # Switch to idle if target is idle mode and current is not idle
        if target_mode in [HVACMode.DRY, HVACMode.FAN]:
            if current_mode not in ["dry", "fan"]:
                self.log(
                    f"Should switch to idle: target={target_mode.value}, current={current_mode}"
                )
                return True
            else:
                self.log(
                    f"Already in idle mode: target={target_mode.value}, current={current_mode}"
                )

        return False

    def _switch_to_idle_mode(self, target_mode: HVACMode):
        """Switch to idle mode without activating the algorithm."""
        self.log(f"🔵 SWITCHING TO IDLE MODE: {target_mode.value}")

        # Save current target temperatures to sensor entities before mode change
        self._save_zone_targets_to_sensors()

        # Set HVAC mode to idle
        self.executor.set_hvac_mode(target_mode)

        # Set all active zone dampers to minimum
        active_zones = self.state_manager.get_active_zones()
        self.log(f"Setting minimum dampers for active zones: {active_zones}")
        self.executor.set_minimum_dampers(self.state_manager)

        self.log(f"✅ Switched to idle mode {target_mode.value} successfully")

    def _activate_algorithm(self, target_mode: HVACMode):
        """Activate the smart algorithm."""
        self.log(f"🔥 ACTIVATING ALGORITHM in {target_mode.value} mode")

        # Store target mode for delayed execution
        self._pending_activation_mode = target_mode

        # Step 1: Set HVAC mode first (from idle to active mode)
        self.log(f"Step 1: Setting HVAC mode to {target_mode.value}")
        self.executor.set_hvac_mode(target_mode)

        # Step 2: Wait for mode change, then restore temperatures
        self.log("Step 2: Waiting for HVAC mode change, then will restore temperatures...")
        self.run_in(self._restore_temperatures_after_mode_change, 3)  # 3 second delay

    def _restore_temperatures_after_mode_change(self, kwargs):
        """Restore temperatures after HVAC mode change."""
        target_mode = self._pending_activation_mode
        self.log(f"Step 2: Restoring target temperatures for {target_mode.value} mode")

        # Restore target temperatures from sensors after mode change
        self._restore_zone_targets_from_sensors()

        # Step 3: Wait for temperature restoration, then set dampers
        self.log("Step 3: Waiting for temperature restoration, then will set dampers...")
        self.run_in(self._complete_algorithm_activation, 3)  # Another 3 second delay

    def _complete_algorithm_activation(self, kwargs):
        """Complete algorithm activation after temperature restoration delay."""
        target_mode = self._pending_activation_mode
        self.log(f"Step 3: Completing algorithm activation for {target_mode.value} mode")

        # Verify temperature restoration
        self._verify_temperature_restoration()

        # Update zone states with restored temperatures before calculating dampers
        self.log("Updating zone states after temperature restoration")
        self.state_manager.update_all_zones()

        # Calculate and set damper positions
        if target_mode == HVACMode.HEAT:
            trigger_zones = self.state_manager.get_zones_needing_heating()
            self.log(f"Trigger zones for heating: {trigger_zones}")
        else:  # COOL
            trigger_zones = self.state_manager.get_zones_needing_cooling()
            self.log(f"Trigger zones for cooling: {trigger_zones}")

        damper_positions = self.decision_engine.calculate_damper_positions(
            self.state_manager, trigger_zones, target_mode
        )
        self.log(f"Calculated damper positions: {damper_positions}")
        self.executor.set_damper_positions(damper_positions, self.state_manager)

        # Update algorithm state
        self.algorithm_active = True
        self.current_algorithm_mode = target_mode
        self.monitor.start_monitoring()
        self.log(f"✅ Algorithm activated successfully")

    def _deactivate_algorithm(self):
        """Deactivate the smart algorithm and return to idle mode."""
        self.log(f"🔵 DEACTIVATING ALGORITHM - returning to idle mode")

        # Save current target temperatures to sensor entities before mode change
        self._save_zone_targets_to_sensors()

        # Get current config
        current_config = self.config_manager.get_config()

        # Set appropriate idle mode using automatic logic
        idle_mode = self.decision_engine.get_idle_mode(current_config.smart_hvac_mode)
        self.log(
            f"Setting idle mode to {idle_mode.value} (smart_hvac_mode: {current_config.smart_hvac_mode})"
        )
        self.executor.set_hvac_mode(idle_mode)

        # Set dampers to minimum for active zones
        active_zones = self.state_manager.get_active_zones()
        self.log(f"Setting minimum dampers for active zones: {active_zones}")
        self.executor.set_minimum_dampers(self.state_manager)

        # Reset algorithm state
        self.algorithm_active = False
        self.current_algorithm_mode = None
        self.monitor.stop_monitoring()
        self.log(f"✅ Algorithm deactivated successfully")

    def _save_zone_targets_to_sensors(self):
        """Save current zone target temperatures to sensor entities."""
        for zone_name, zone in self.state_manager.zones.items():
            if zone.is_active:
                sensor_entity = f"sensor.smart_aircon_{zone_name}_target_temp"
                try:
                    self.set_state(
                        sensor_entity,
                        state=zone.target_temp,
                        attributes={
                            "unit_of_measurement": "°C",
                            "friendly_name": f"Smart Aircon {zone_name.title()} Target Temperature",
                            "device_class": "temperature",
                            "source": "smart_aircon_controller",
                            "zone": zone_name,
                        }
                    )
                    self.log(f"Saved {zone_name} target temp to sensor: {zone.target_temp}°C")
                except Exception as e:
                    self.log(f"Error saving target temp for {zone_name}: {e}")

    def _restore_zone_targets_from_sensors(self):
        """Restore zone target temperatures from sensor entities to climate entities."""
        for zone_name, zone in self.state_manager.zones.items():
            if zone.is_active:
                sensor_entity = f"sensor.smart_aircon_{zone_name}_target_temp"
                try:
                    sensor_state = self.get_state(sensor_entity)
                    if sensor_state not in ["unavailable", "unknown", None]:
                        stored_target = float(sensor_state)
                        
                        # Set the target temperature back to the climate entity
                        self.call_service(
                            "climate/set_temperature",
                            entity_id=zone.entity_id,
                            temperature=stored_target,
                        )
                        self.log(f"Restored {zone_name} target temperature to {stored_target}°C")
                    else:
                        self.log(f"No stored target temperature found for {zone_name}")
                except Exception as e:
                    self.log(f"Error restoring target temperature for {zone_name}: {e}")

    def _verify_temperature_restoration(self):
        """Verify that zone target temperatures have been properly restored."""
        for zone_name, zone in self.state_manager.zones.items():
            if zone.is_active:
                sensor_entity = f"sensor.smart_aircon_{zone_name}_target_temp"
                try:
                    # Get expected target from sensor
                    sensor_state = self.get_state(sensor_entity)
                    if sensor_state not in ["unavailable", "unknown", None]:
                        expected_target = float(sensor_state)
                        
                        # Get actual target from climate entity
                        climate_entity = self.get_entity(zone.entity_id)
                        actual_target = climate_entity.attributes.get("temperature", 0.0)
                        actual_target = float(actual_target) if actual_target is not None else 0.0
                        
                        if abs(actual_target - expected_target) < 0.1:  # Within 0.1°C tolerance
                            self.log(f"✅ {zone_name} target temperature verified: {actual_target}°C")
                        else:
                            self.log(f"⚠️ {zone_name} target mismatch: expected {expected_target}°C, got {actual_target}°C")
                except Exception as e:
                    self.log(f"Error verifying target temperature for {zone_name}: {e}")

    def _get_effective_target_temp(self, zone_name: str, current_target: float) -> float:
        """Get effective target temperature - use stored sensor value if in idle mode."""
        # If in idle mode (DRY/FAN), try to use stored target temp
        if self.state_manager.current_hvac_mode in ["dry", "fan"]:
            sensor_entity = f"sensor.smart_aircon_{zone_name}_target_temp"
            try:
                sensor_state = self.get_state(sensor_entity)
                if sensor_state not in ["unavailable", "unknown", None]:
                    stored_target = float(sensor_state)
                    self.log(f"Using stored target for {zone_name}: {stored_target}°C (current: {current_target}°C)")
                    return stored_target
            except Exception as e:
                self.log(f"Error reading stored target for {zone_name}: {e}")
        
        # Use current target temperature
        return current_target

    def toggle_controller(self, enabled: bool):
        """Enable or disable the smart controller."""
        self.log(
            "INFO: Controller enabled/disabled status should be changed via Home Assistant entity"
        )
        self.log(
            f"Current status can be viewed in: {self.config_manager.config_entities.get('enabled', 'N/A')}"
        )

    def set_smart_hvac_mode(self, mode: str):
        """Set the desired HVAC mode (heat or cool)."""
        self.log("INFO: Smart HVAC mode should be changed via Home Assistant entity")
        self.log(
            f"Current mode can be changed in: {self.config_manager.config_entities.get('smart_hvac_mode', 'N/A')}"
        )

    def get_status(self) -> Dict:
        """Get current status of the controller."""
        self.state_manager.update_all_zones()

        active_zones = self.state_manager.get_active_zones()

        return {
            "enabled": self.config.enabled,
            "algorithm_active": self.algorithm_active,
            "current_hvac_mode": self.state_manager.current_hvac_mode,
            "smart_hvac_mode": self.config.smart_hvac_mode,
            "algorithm_mode": (
                self.current_algorithm_mode.value
                if self.current_algorithm_mode
                else None
            ),
            "active_zones": active_zones,
            "zone_states": {
                name: {
                    "current_temp": zone.current_temp,
                    "target_temp": zone.target_temp,
                    "is_active": zone.is_active,
                    "damper_position": zone.damper_position,
                }
                for name, zone in self.state_manager.zones.items()
            },
        }
