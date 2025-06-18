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
    minimum_damper_percent: int = 5  # Minimum damper for active zones to keep them on
    heating_mode: str = "heat"
    idle_mode: str = "dry"
    cooling_mode: str = "cool"
    smart_hvac_mode: str = "heat"  # Desired seasonal mode: heat or cool
    # Fallback mechanism for Airtouch controller interference
    algorithm_timeout_minutes: int = 30  # Max time before fallback
    stability_check_minutes: int = 10  # Time to check for temperature stability
    progress_timeout_minutes: int = 15  # Time without progress before fallback


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

        # Fallback mechanism tracking
        self.algorithm_start_time: Optional[datetime.datetime] = None
        self.temperature_history: Dict[str, List[Tuple[datetime.datetime, float]]] = {}
        self.last_progress_time: Optional[datetime.datetime] = None

        # Load zone configurations
        self._initialize_zones()

        # Set up periodic checking
        if self.config.enabled:
            # Use string format for start time - "now+10" means start in 10 seconds
            self.run_every(
                self._periodic_check,
                "now+10",
                self.config.check_interval,
            )
            self.log(
                f"Periodic check scheduled to start in 10 seconds, running every {self.config.check_interval} seconds"
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
            cooling_mode=self.args.get("cooling_mode", "cool"),
            smart_hvac_mode=self.args.get("smart_hvac_mode", "heat"),
            minimum_damper_percent=self.args.get("minimum_damper_percent", 5),
            algorithm_timeout_minutes=self.args.get("algorithm_timeout_minutes", 30),
            stability_check_minutes=self.args.get("stability_check_minutes", 10),
            progress_timeout_minutes=self.args.get("progress_timeout_minutes", 15),
        )

    def _initialize_zones(self):
        """Initialize zone configurations from config"""
        zones_config = self.args.get("zones", {})
        self.log(f"DEBUG: zones_config from args: {zones_config}")
        self.log(f"DEBUG: Number of zones to initialize: {len(zones_config)}")

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
                    self.log(
                        f"Warning: Climate entity {climate_entity} not found during startup - will retry later"
                    )

                if not damper_exists:
                    self.log(
                        f"Warning: Damper entity {damper_entity} not found during startup - will retry later"
                    )

                # Create zone state even if entities aren't found yet
                # They may become available after Home Assistant fully loads
                zone_state = ZoneState(
                    entity_id=climate_entity,
                    damper_entity=damper_entity,
                    current_temp=0.0,
                    target_temp=0.0,
                    is_active=False,
                    isolation=zone_config.get("isolation", False),
                )

                self.zones[zone_name] = zone_state
                self.log(
                    f"Initialized zone: {zone_name} (entities available: climate={climate_exists}, damper={damper_exists})"
                )

            except KeyError as e:
                self.log(
                    f"Error initializing zone {zone_name}: Missing config {e}"
                )
            except Exception as e:
                self.log(f"Error initializing zone {zone_name}: {e}")
        
        self.log(f"DEBUG: Zones initialized: {len(self.zones)} zones")
        self.log(f"DEBUG: Zone names: {list(self.zones.keys())}")

    def _entity_exists(self, entity_id: str) -> bool:
        """Check if an entity exists in Home Assistant"""
        try:
            entity = self.get_entity(entity_id)
            state = entity.get_state()
            # Entity exists if state is not None and not "unavailable"
            # During startup, entities might be "unavailable" temporarily
            exists = state is not None and state != "unavailable"
            self.log(
                f"DEBUG: Entity {entity_id} exists: {exists}, state: {state}"
            )
            return exists
        except Exception as e:
            self.log(f"Error checking entity {entity_id}: {e}")
            return False

    def _validate_entities(self, kwargs):
        """Validate all entities after Home Assistant has fully loaded"""
        self.log("Validating entities after startup...")

        # Check main climate entity using Entity API
        try:
            main_entity = self.get_entity(self.config.main_climate)
            main_state = main_entity.get_state()
            self.log(
                f"DEBUG: Main climate {self.config.main_climate} state: {main_state}, attributes: {main_entity.attributes}"
            )

            if not self._entity_exists(self.config.main_climate):
                self.log(
                    f"ERROR: Main climate entity {self.config.main_climate} not found!"
                )
            else:
                self.log(f"Main climate entity {self.config.main_climate} validated")
        except Exception as e:
            self.log(f"ERROR: Exception validating main climate entity: {e}")

        # Check all zone entities
        missing_entities = []
        for zone_name, zone in self.zones.items():
            try:
                # Debug log entity states using Entity API
                climate_entity = self.get_entity(zone.entity_id)
                damper_entity = self.get_entity(zone.damper_entity)

                climate_state = climate_entity.get_state()
                damper_state = damper_entity.get_state()

                self.log(
                    f"DEBUG: Zone {zone_name} climate entity {zone.entity_id}: state={climate_state}, attrs={climate_entity.attributes}",
                    level="DEBUG",
                )
                self.log(
                    f"DEBUG: Zone {zone_name} damper entity {zone.damper_entity}: state={damper_state}, attrs={damper_entity.attributes}",
                    level="DEBUG",
                )

                climate_exists = self._entity_exists(zone.entity_id)
                damper_exists = self._entity_exists(zone.damper_entity)

                if not climate_exists:
                    missing_entities.append(f"{zone_name}: {zone.entity_id}")
                if not damper_exists:
                    missing_entities.append(f"{zone_name}: {zone.damper_entity}")

                if climate_exists and damper_exists:
                    self.log(f"Zone {zone_name}: All entities validated")
                    # Try to get initial state
                    self._update_single_zone_state(zone_name, zone)
                else:
                    self.log(
                        f"Zone {zone_name}: Missing entities - climate={climate_exists}, damper={damper_exists}",
                        level="WARNING",
                    )

            except Exception as e:
                self.log(f"ERROR: Exception validating zone {zone_name}: {e}")

        if missing_entities:
            self.log(
                f"The following entities are still missing after startup: {missing_entities}",
                level="ERROR",
            )
            self.log(
                "Please check your Home Assistant configuration and entity names",
                level="ERROR",
            )
        else:
            self.log("All entities validated successfully!")

    def _periodic_check(self, kwargs):
        """Periodic check function called every check_interval seconds"""
        self.log("DEBUG: Periodic check called")

        if not self.config.enabled:
            self.log("DEBUG: Controller disabled, skipping periodic check")
            return

        try:
            self.log("DEBUG: Starting periodic check")
            self.last_check_time = datetime.datetime.now()
            self._update_zone_states()

            # Get current HVAC mode for logging/status only
            current_hvac_mode = self._get_current_hvac_mode()
            self.log(
                f"DEBUG: Current HVAC mode: {current_hvac_mode}, Smart HVAC mode: {self.config.smart_hvac_mode}",
                level="DEBUG",
            )

            # Determine which zones need attention based on smart_hvac_mode (desired mode)
            if self.config.smart_hvac_mode == "heat":
                zones_needing_attention = self._analyze_zones_for_heating()
                target_mode = HVACMode.HEAT
            elif self.config.smart_hvac_mode == "cool":
                zones_needing_attention = self._analyze_zones_for_cooling()
                target_mode = HVACMode.COOL
            else:
                self.log(
                    f"Invalid smart_hvac_mode: {self.config.smart_hvac_mode}",
                    level="ERROR",
                )
                return

            self.log(
                f"DEBUG: Zones needing {self.config.smart_hvac_mode}: {zones_needing_attention}",
                level="DEBUG",
            )

            # If algorithm is already running in the correct mode
            if self.algorithm_active and self.algorithm_mode == target_mode:
                if self._all_zones_satisfied():
                    self.log("Current cycle complete.")
                    self._deactivate_algorithm()
                else:
                    self.log(
                        f"DEBUG: {target_mode.value.title()} cycle continues. Letting Airtouch control dampers.",
                        level="DEBUG",
                    )
                return

            # If algorithm is running in wrong mode, deactivate it
            if self.algorithm_active and self.algorithm_mode != target_mode:
                self.log(
                    f"Smart HVAC mode changed from {self.algorithm_mode.value} to {target_mode.value}, deactivating algorithm"
                )
                self._deactivate_algorithm()
                return

            # If algorithm is NOT active, start it if zones need attention
            if zones_needing_attention:
                self._execute_smart_algorithm(zones_needing_attention, target_mode)

        except Exception as e:
            self.log(f"Error in periodic check: {e}")

    def _update_zone_states(self):
        """Update current state of all zones using proper AppDaemon Entity API"""
        self.log("DEBUG: Starting zone state update")
        self.log(f"DEBUG: Number of zones to update: {len(self.zones)}")
        self.log(f"DEBUG: Zone names: {list(self.zones.keys())}")

        for zone_name, zone in self.zones.items():
            self.log(f"DEBUG: Processing zone {zone_name}")
            try:
                self.log(f"DEBUG: Updating zone {zone_name} with entity {zone.entity_id}")

                # Use AppDaemon Entity API for climate entity
                climate_entity = self.get_entity(zone.entity_id)
                climate_state = climate_entity.get_state()

                self.log(
                    f"DEBUG: Zone {zone_name} climate state: {climate_state}",
                    level="DEBUG",
                )

                if climate_state in ["unavailable", "unknown", None]:
                    self.log(
                        f"WARNING: Entity {zone.entity_id} state is {climate_state}",
                        level="WARNING",
                    )
                    continue

                # Update zone state from climate entity
                zone.is_active = climate_state not in [
                    "off",
                    "unavailable",
                    "unknown",
                    None,
                ]

                # Get temperature values from attributes
                target_temp = climate_entity.attributes.get("temperature", 0.0)
                current_temp = climate_entity.attributes.get("current_temperature", 0.0)

                zone.target_temp = (
                    float(target_temp) if target_temp is not None else 0.0
                )
                zone.current_temp = (
                    float(current_temp) if current_temp is not None else 0.0
                )

                self.log(
                    f"DEBUG: Zone {zone_name} - active: {zone.is_active}, current: {zone.current_temp}°C, target: {zone.target_temp}°C",
                    level="DEBUG",
                )

                # Use AppDaemon Entity API for damper entity
                damper_entity = self.get_entity(zone.damper_entity)
                damper_position = damper_entity.attributes.get("current_position", 0)
                zone.damper_position = (
                    int(damper_position) if damper_position is not None else 0
                )

                self.log(f"DEBUG: Zone {zone_name} damper position: {zone.damper_position}%")

                # Track temperature history for fallback mechanism
                self._update_temperature_history(zone_name, zone.current_temp)
                
                self.log(f"DEBUG: Zone {zone_name} update completed successfully")

            except (ValueError, TypeError) as e:
                self.log(f"Error processing state for zone {zone_name}: {e}")
            except Exception as e:
                self.log(f"Error updating zone {zone_name}: {e}")
                self.log(
                    f"DEBUG: Full exception: {type(e).__name__}: {str(e)}",
                    level="DEBUG",
                )

    def _get_current_hvac_mode(self) -> str:
        """Get the current HVAC mode from the main climate entity"""
        try:
            main_entity = self.get_entity(self.config.main_climate)
            current_mode = main_entity.get_state()
            return current_mode if current_mode else "unknown"
        except Exception as e:
            self.log(f"Error getting current HVAC mode: {e}")
            return "unknown"

    def _analyze_zones_for_heating(self) -> List[str]:
        """Analyze zones to determine which need heating"""
        zones_needing_heating = []

        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue

            # Check if zone needs heating
            if zone.current_temp <= (zone.target_temp - self.config.temp_tolerance):
                zones_needing_heating.append(zone_name)
                self.log(
                    f"Zone {zone_name} needs heating: {zone.current_temp}°C <= {zone.target_temp - self.config.temp_tolerance}°C"
                )

        return zones_needing_heating

    def _analyze_zones_for_cooling(self) -> List[str]:
        """Analyze zones to determine which need cooling"""
        zones_needing_cooling = []

        for zone_name, zone in self.zones.items():
            if not zone.is_active:
                continue

            # Check if zone needs cooling
            if zone.current_temp >= (zone.target_temp + self.config.temp_tolerance):
                zones_needing_cooling.append(zone_name)
                self.log(
                    f"Zone {zone_name} needs cooling: {zone.current_temp}°C >= {zone.target_temp + self.config.temp_tolerance}°C"
                )

        return zones_needing_cooling

    def _analyze_zones(self) -> Tuple[List[str], List[str]]:
        """Legacy method - kept for compatibility"""
        return self._analyze_zones_for_heating(), self._analyze_zones_for_cooling()

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

        # Set start time for fallback mechanism
        if not self.algorithm_start_time:
            self.algorithm_start_time = datetime.datetime.now()
            self.last_progress_time = datetime.datetime.now()
            self.log(
                f"Algorithm started at {self.algorithm_start_time}, tracking for fallback"
            )

    def _calculate_damper_positions(
        self, trigger_zones: List[str], mode: HVACMode
    ) -> Dict[str, int]:
        """Calculate optimal damper positions for all zones"""
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
                            damper_positions[zone_name] = (
                                self.config.secondary_damper_percent
                            )
                        else:
                            # Zone is above target but below target + tolerance - minimal damper
                            damper_positions[zone_name] = (
                                self.config.overflow_damper_percent
                            )
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
                            damper_positions[zone_name] = (
                                self.config.secondary_damper_percent
                            )
                        else:
                            # Zone is below target but above target - tolerance - minimal damper
                            damper_positions[zone_name] = (
                                self.config.overflow_damper_percent
                            )
                    else:
                        # Zone is at or below target - tolerance - minimum damper to keep active
                        damper_positions[zone_name] = self.config.minimum_damper_percent

        return damper_positions

    def _apply_damper_positions(self, positions: Dict[str, int]):
        """Apply calculated damper positions"""
        for zone_name, position in positions.items():
            if zone_name not in self.zones:
                continue

            zone = self.zones[zone_name]
            try:
                # Always set position - never close dampers for active zones
                self.call_service(
                    "cover/set_cover_position",
                    entity_id=zone.damper_entity,
                    position=position,
                )
                self.log(f"Set {zone_name} damper to {position}%")

            except Exception as e:
                self.log(f"Error setting damper for {zone_name}: {e}")

    def _set_hvac_mode(self, mode: HVACMode):
        """Set the main HVAC system mode"""
        try:
            main_entity = self.get_entity(self.config.main_climate)
            current_mode = main_entity.get_state()

            if current_mode != mode.value:
                self.call_service(
                    "climate/set_hvac_mode",
                    entity_id=self.config.main_climate,
                    hvac_mode=mode.value,
                )
                self.current_hvac_mode = mode.value
                self.log(f"Set HVAC mode to {mode.value}")
        except Exception as e:
            self.log(f"Error setting HVAC mode: {e}")

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
            fallback_satisfied = self._check_fallback_satisfaction(
                now, algorithm_runtime
            )
            if fallback_satisfied:
                return True

        return False

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

    def _check_fallback_satisfaction(
        self, now: datetime.datetime, algorithm_runtime: datetime.timedelta
    ) -> bool:
        """Check fallback criteria for when Airtouch interferes with our algorithm"""

        # Fallback criteria 1: Maximum timeout reached
        if (
            algorithm_runtime.total_seconds()
            >= self.config.algorithm_timeout_minutes * 60
        ):
            self.log(
                f"Fallback: Algorithm timeout reached ({self.config.algorithm_timeout_minutes} minutes)"
            )
            return True

        # Check if all zones are at least at target (not target + tolerance)
        zones_at_target = self._all_zones_at_target()
        if not zones_at_target:
            return False  # Can't use fallback if zones aren't even at target

        # Fallback criteria 2: No progress for extended time
        if self.last_progress_time:
            time_since_progress = now - self.last_progress_time
            if (
                time_since_progress.total_seconds()
                >= self.config.progress_timeout_minutes * 60
            ):
                self.log(
                    f"Fallback: No progress for {self.config.progress_timeout_minutes} minutes - Airtouch likely controlling dampers"
                )
                return True

        # Fallback criteria 3: Temperature stability (zones stable for extended time)
        if self._zones_stable_for_time(now, self.config.stability_check_minutes):
            self.log(
                f"Fallback: Zones stable for {self.config.stability_check_minutes} minutes - assuming Airtouch control"
            )
            return True

        # Fallback criteria 4: Most dampers closed (indicating Airtouch control)
        if self._most_dampers_closed():
            self.log("Fallback: Most dampers closed - Airtouch has taken control")
            return True

        return False

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
                temp
                for time, temp in self.temperature_history[zone_name]
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

    def _deactivate_algorithm(self):
        """Deactivate the smart algorithm and return to idle mode"""
        self.log("All zones satisfied, deactivating algorithm")

        # Set HVAC to idle mode
        self._set_hvac_mode(HVACMode.DRY)

        # Close all dampers gradually (let Airtouch handle it)
        # We don't force close dampers to let the normal system take over

        self.algorithm_active = False
        self.algorithm_mode = None

        # Reset fallback tracking
        self.algorithm_start_time = None
        self.temperature_history.clear()
        self.last_progress_time = None

    def _update_temperature_history(self, zone_name: str, current_temp: float):
        """Update temperature history for fallback mechanism"""
        now = datetime.datetime.now()

        # Initialize history for new zones
        if zone_name not in self.temperature_history:
            self.temperature_history[zone_name] = []

        # Add current reading
        self.temperature_history[zone_name].append((now, current_temp))

        # Keep only last 30 minutes of data
        cutoff_time = now - datetime.timedelta(minutes=30)
        self.temperature_history[zone_name] = [
            (time, temp)
            for time, temp in self.temperature_history[zone_name]
            if time > cutoff_time
        ]

        # Check for progress (used for fallback)
        if self.algorithm_active and len(self.temperature_history[zone_name]) >= 2:
            # Get temperature from 5 minutes ago
            five_min_ago = now - datetime.timedelta(minutes=5)
            old_readings = [
                (time, temp)
                for time, temp in self.temperature_history[zone_name]
                if time <= five_min_ago
            ]

            if old_readings:
                old_temp = old_readings[-1][1]  # Most recent old reading
                progress_threshold = 0.1  # 0.1°C progress threshold

                if self.algorithm_mode == HVACMode.HEAT:
                    # Progress means temperature is increasing
                    if current_temp > old_temp + progress_threshold:
                        self.last_progress_time = now
                elif self.algorithm_mode == HVACMode.COOL:
                    # Progress means temperature is decreasing
                    if current_temp < old_temp - progress_threshold:
                        self.last_progress_time = now

    def toggle_controller(self, state: bool):
        """Enable or disable the smart controller"""
        self.config.enabled = state
        self.log(f"Smart controller {'enabled' if state else 'disabled'}")

        if not state and self.algorithm_active:
            self._deactivate_algorithm()

    def set_smart_hvac_mode(self, mode: str):
        """Set the desired HVAC mode (heat or cool)"""
        if mode not in ["heat", "cool"]:
            self.log(
                f"Invalid smart HVAC mode: {mode}. Must be 'heat' or 'cool'",
                level="ERROR",
            )
            return

        old_mode = self.config.smart_hvac_mode
        self.config.smart_hvac_mode = mode
        self.log(f"Smart HVAC mode changed from {old_mode} to {mode}")

        # If algorithm is active in wrong mode, deactivate it
        if self.algorithm_active and self.algorithm_mode:
            if (mode == "heat" and self.algorithm_mode != HVACMode.HEAT) or (
                mode == "cool" and self.algorithm_mode != HVACMode.COOL
            ):
                self.log("Deactivating algorithm due to mode change")
                self._deactivate_algorithm()

    def _update_single_zone_state(self, zone_name: str, zone: ZoneState):
        """Update state for a single zone - helper method for debugging"""
        try:
            climate_entity = self.get_entity(zone.entity_id)
            climate_state = climate_entity.get_state()

            if climate_state not in ["unavailable", "unknown", None]:
                zone.is_active = climate_state not in [
                    "off",
                    "unavailable",
                    "unknown",
                    None,
                ]
                zone.target_temp = float(
                    climate_entity.attributes.get("temperature", 0.0)
                )
                zone.current_temp = float(
                    climate_entity.attributes.get("current_temperature", 0.0)
                )

            # Get damper position
            damper_entity = self.get_entity(zone.damper_entity)
            zone.damper_position = int(
                damper_entity.attributes.get("current_position", 0)
            )

        except Exception as e:
            self.log(f"Error updating single zone {zone_name}: {e}")

    def get_status(self) -> Dict:
        """Get current status of the controller"""
        # Force update zone states before returning status
        self._update_zone_states()

        active_zones = [name for name, zone in self.zones.items() if zone.is_active]

        self.log(f"DEBUG: get_status called - active zones: {active_zones}")

        # Get current HVAC mode using Entity API
        current_hvac_mode = self.current_hvac_mode
        if not current_hvac_mode:
            try:
                main_entity = self.get_entity(self.config.main_climate)
                current_hvac_mode = main_entity.get_state()
            except:
                current_hvac_mode = "unknown"

        status = {
            "enabled": self.config.enabled,
            "algorithm_active": self.algorithm_active,
            "current_hvac_mode": current_hvac_mode,
            "smart_hvac_mode": self.config.smart_hvac_mode,
            "algorithm_mode": (
                self.algorithm_mode.value if self.algorithm_mode else None
            ),
            "active_zones": active_zones,
            "last_check": (
                self.last_check_time.isoformat() if self.last_check_time else None
            ),
            "zone_states": {
                name: {
                    "current_temp": zone.current_temp,
                    "target_temp": zone.target_temp,
                    "is_active": zone.is_active,
                    "damper_position": zone.damper_position,
                }
                for name, zone in self.zones.items()
            },
        }

        self.log(f"DEBUG: get_status returning: {status}")
        return status
