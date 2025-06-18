import appdaemon.plugins.hass.hassapi as hass
import json


class SmartAirconControllerInterface(hass.Hass):
    """
    Interface for the Smart Aircon Controller
    
    Provides services and sensors for controlling and monitoring the smart controller.
    """

    def initialize(self):
        """Initialize the controller interface"""
        self.log("Initializing Smart Aircon Controller Interface")
        
        # Get reference to the main controller
        self.controller = None
        self._find_controller()
        
        # Register services
        self.register_service("smart_aircon/toggle", self._service_toggle)
        self.register_service("smart_aircon/get_status", self._service_get_status)
        self.register_service("smart_aircon/set_temp_tolerance", self._service_set_temp_tolerance)
        self.register_service("smart_aircon/set_smart_hvac_mode", self._service_set_smart_hvac_mode)
        
        # Create sensor entities for monitoring
        self._create_sensors()
        
        # Update sensors periodically - start after a delay to allow controller to initialize
        self.run_in(self._update_sensors, 10)  # Initial update after 10 seconds
        self.run_every(self._update_sensors, "now+30", 30)  # Update every 30 seconds
        
        self.log("Smart Aircon Controller Interface initialized")

    def _find_controller(self):
        """Find the main controller instance"""
        try:
            # Get the controller from the global app registry
            self.controller = self.get_app("smart_aircon_controller")
            if self.controller:
                self.log("DEBUG: Successfully found Smart Aircon Controller", level="DEBUG")
            else:
                self.log("DEBUG: Smart Aircon Controller returned None", level="DEBUG")
        except Exception as e:
            self.log(f"Warning: Smart Aircon Controller not found: {e}", level="WARNING")
            self.controller = None

    def _service_toggle(self, namespace, domain, service, kwargs):
        """Service to toggle the smart controller on/off"""
        if not self.controller:
            self.log("Controller not available", level="ERROR")
            return
            
        enabled = kwargs.get("enabled", True)
        self.controller.toggle_controller(enabled)
        self.log(f"Smart controller toggled: {enabled}")

    def _service_get_status(self, namespace, domain, service, kwargs):
        """Service to get controller status"""
        if not self.controller:
            return {"error": "Controller not available"}
            
        return self.controller.get_status()

    def _service_set_temp_tolerance(self, namespace, domain, service, kwargs):
        """Service to set temperature tolerance"""
        if not self.controller:
            self.log("Controller not available", level="ERROR")
            return
            
        tolerance = kwargs.get("tolerance", 0.5)
        self.controller.config.temp_tolerance = float(tolerance)
        self.log(f"Temperature tolerance set to: {tolerance}")

    def _service_set_smart_hvac_mode(self, namespace, domain, service, kwargs):
        """Service to set smart HVAC mode (heat or cool)"""
        if not self.controller:
            self.log("Controller not available", level="ERROR")
            return
            
        mode = kwargs.get("mode", "heat")
        self.controller.set_smart_hvac_mode(mode)
        self.log(f"Smart HVAC mode set to: {mode}")

    def _create_sensors(self):
        """Create sensor entities for monitoring"""
        # Controller enabled sensor
        self.set_state(
            "sensor.smart_aircon_enabled",
            state="unknown",
            attributes={
                "friendly_name": "Smart Aircon Enabled",
                "icon": "mdi:air-conditioner"
            }
        )
        
        # Algorithm active sensor
        self.set_state(
            "sensor.smart_aircon_algorithm_active",
            state="unknown",
            attributes={
                "friendly_name": "Smart Aircon Algorithm Active",
                "icon": "mdi:cog"
            }
        )
        
        # Current HVAC mode sensor
        self.set_state(
            "sensor.smart_aircon_hvac_mode",
            state="unknown",
            attributes={
                "friendly_name": "Smart Aircon HVAC Mode",
                "icon": "mdi:hvac"
            }
        )
        
        # Smart HVAC mode sensor (desired mode)
        self.set_state(
            "sensor.smart_aircon_smart_hvac_mode",
            state="unknown",
            attributes={
                "friendly_name": "Smart Aircon Desired Mode",
                "icon": "mdi:target"
            }
        )
        
        # Active zones sensor
        self.set_state(
            "sensor.smart_aircon_active_zones",
            state="unknown",
            attributes={
                "friendly_name": "Smart Aircon Active Zones",
                "icon": "mdi:home-thermometer"
            }
        )

    def _update_sensors(self, kwargs):
        """Update sensor states"""
        if not self.controller:
            self.log("DEBUG: Controller not available for sensor update", level="DEBUG")
            return
            
        try:
            self.log("DEBUG: Updating sensors - getting controller status", level="DEBUG")
            status = self.controller.get_status()
            self.log(f"DEBUG: Controller status: {status}", level="DEBUG")
            
            # Update enabled sensor
            self.set_state(
                "sensor.smart_aircon_enabled",
                state="on" if status["enabled"] else "off"
            )
            
            # Update algorithm active sensor
            self.set_state(
                "sensor.smart_aircon_algorithm_active",
                state="on" if status["algorithm_active"] else "off"
            )
            
            # Update HVAC mode sensor
            hvac_mode = status.get("current_hvac_mode", "unknown")
            self.set_state(
                "sensor.smart_aircon_hvac_mode",
                state=hvac_mode
            )
            
            # Update smart HVAC mode sensor (desired mode)
            smart_hvac_mode = status.get("smart_hvac_mode", "heat")
            self.set_state(
                "sensor.smart_aircon_smart_hvac_mode",
                state=smart_hvac_mode
            )
            
            # Update active zones sensor with detailed information
            active_zones = status.get("active_zones", [])
            zone_states = status.get("zone_states", {})
            
            # Create detailed zone information for attributes
            zone_details = {}
            for zone_name, zone_data in zone_states.items():
                zone_details[zone_name] = {
                    "current_temp": zone_data.get("current_temp", 0),
                    "target_temp": zone_data.get("target_temp", 0),
                    "is_active": zone_data.get("is_active", False),
                    "damper_position": zone_data.get("damper_position", 0)
                }
            
            self.log(f"DEBUG: Updating active zones sensor - count: {len(active_zones)}, zones: {active_zones}, details: {zone_details}", level="DEBUG")
            
            self.set_state(
                "sensor.smart_aircon_active_zones",
                state=len(active_zones),
                attributes={
                    "zones": active_zones,
                    "zone_details": zone_details,
                    "friendly_name": "Smart Aircon Active Zones",
                    "icon": "mdi:home-thermometer",
                    "last_updated": status.get("last_check", "never")
                }
            )
            
            self.log("DEBUG: Sensors updated successfully", level="DEBUG")
            
        except Exception as e:
            self.log(f"Error updating sensors: {e}", level="ERROR")
            import traceback
            self.log(f"DEBUG: Sensor update traceback: {traceback.format_exc()}", level="DEBUG") 