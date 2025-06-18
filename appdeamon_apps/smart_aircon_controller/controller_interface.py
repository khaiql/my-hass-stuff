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
        
        # Create sensor entities for monitoring
        self._create_sensors()
        
        # Update sensors periodically
        self.run_every(self._update_sensors, "now", 60)  # Update every minute
        
        self.log("Smart Aircon Controller Interface initialized")

    def _find_controller(self):
        """Find the main controller instance"""
        try:
            # Get the controller from the global app registry
            self.controller = self.get_app("smart_aircon_controller")
        except:
            self.log("Warning: Smart Aircon Controller not found", level="WARNING")

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
            return
            
        try:
            status = self.controller.get_status()
            
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
            self.set_state(
                "sensor.smart_aircon_hvac_mode",
                state=status.get("current_hvac_mode", "unknown")
            )
            
            # Update active zones sensor
            active_zones = status.get("active_zones", [])
            self.set_state(
                "sensor.smart_aircon_active_zones",
                state=len(active_zones),
                attributes={
                    "zones": active_zones,
                    "zone_details": status.get("zone_states", {}),
                    "friendly_name": "Smart Aircon Active Zones",
                    "icon": "mdi:home-thermometer"
                }
            )
            
        except Exception as e:
            self.log(f"Error updating sensors: {e}", level="ERROR") 