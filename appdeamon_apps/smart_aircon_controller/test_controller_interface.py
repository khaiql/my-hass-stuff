import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the current directory to sys.path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock AppDaemon before importing our modules
class MockHass:
    """Mock AppDaemon Hass class"""
    def __init__(self):
        pass

# Mock the appdaemon module
mock_hass_module = MagicMock()
mock_hass_module.Hass = MockHass

sys.modules['appdaemon'] = MagicMock()
sys.modules['appdaemon.plugins'] = MagicMock()
sys.modules['appdaemon.plugins.hass'] = MagicMock()
sys.modules['appdaemon.plugins.hass.hassapi'] = mock_hass_module

# Now import our modules
from controller_interface import SmartAirconControllerInterface


class TestSmartAirconControllerInterface(unittest.TestCase):
    """Test cases for the Smart Aircon Controller Interface"""

    def setUp(self):
        """Set up test fixtures"""
        # Create interface instance with mocked dependencies
        self.interface = SmartAirconControllerInterface()
        self.interface.log = Mock()
        self.interface.get_app = Mock()
        self.interface.register_service = Mock()
        self.interface.set_state = Mock()
        self.interface.run_every = Mock()
        
        # Mock the main controller
        self.mock_controller = Mock()
        self.interface.controller = self.mock_controller

    def test_initialization(self):
        """Test interface initialization"""
        # Call initialize method
        self.interface.initialize()
        
        # Verify services were registered
        expected_services = [
            "smart_aircon/toggle",
            "smart_aircon/get_status", 
            "smart_aircon/set_temp_tolerance"
        ]
        
        # Check that register_service was called
        self.assertEqual(self.interface.register_service.call_count, 3)

    def test_service_toggle_enable(self):
        """Test toggle service - enable"""
        kwargs = {"enabled": True}
        
        self.interface._service_toggle("namespace", "domain", "service", kwargs)
        
        # Verify controller was called
        self.mock_controller.toggle_controller.assert_called_once_with(True)

    def test_service_toggle_disable(self):
        """Test toggle service - disable"""
        kwargs = {"enabled": False}
        
        self.interface._service_toggle("namespace", "domain", "service", kwargs)
        
        # Verify controller was called
        self.mock_controller.toggle_controller.assert_called_once_with(False)

    def test_service_toggle_no_controller(self):
        """Test toggle service when controller is not available"""
        self.interface.controller = None
        kwargs = {"enabled": True}
        
        # Should not raise exception
        self.interface._service_toggle("namespace", "domain", "service", kwargs)
        
        # Verify error was logged
        self.interface.log.assert_called_with(
            "Controller not available",
            level="ERROR"
        )

    def test_service_get_status(self):
        """Test get status service"""
        expected_status = {
            "enabled": True,
            "algorithm_active": False,
            "active_zones": ["living"]
        }
        self.mock_controller.get_status.return_value = expected_status
        
        result = self.interface._service_get_status("namespace", "domain", "service", {})
        
        # Verify controller was called and result returned
        self.mock_controller.get_status.assert_called_once()
        self.assertEqual(result, expected_status)

    def test_service_get_status_no_controller(self):
        """Test get status service when controller is not available"""
        self.interface.controller = None
        
        result = self.interface._service_get_status("namespace", "domain", "service", {})
        
        # Should return error
        self.assertEqual(result, {"error": "Controller not available"})

    def test_service_set_temp_tolerance(self):
        """Test set temperature tolerance service"""
        kwargs = {"tolerance": 0.7}
        
        self.interface._service_set_temp_tolerance("namespace", "domain", "service", kwargs)
        
        # Verify controller config was updated
        self.assertEqual(self.mock_controller.config.temp_tolerance, 0.7)

    def test_service_set_temp_tolerance_default(self):
        """Test set temperature tolerance service with default value"""
        kwargs = {}  # No tolerance specified
        
        self.interface._service_set_temp_tolerance("namespace", "domain", "service", kwargs)
        
        # Verify default tolerance was set
        self.assertEqual(self.mock_controller.config.temp_tolerance, 0.5)

    def test_create_sensors(self):
        """Test sensor creation"""
        self.interface._create_sensors()
        
        # Verify sensors were created
        expected_sensors = [
            "sensor.smart_aircon_enabled",
            "sensor.smart_aircon_algorithm_active",
            "sensor.smart_aircon_hvac_mode",
            "sensor.smart_aircon_active_zones"
        ]
        
        # Check that set_state was called for each sensor
        self.assertEqual(self.interface.set_state.call_count, 4)

    def test_update_sensors(self):
        """Test sensor updates"""
        # Mock controller status
        mock_status = {
            "enabled": True,
            "algorithm_active": False,
            "current_hvac_mode": "dry",
            "active_zones": ["living", "study"],
            "zone_states": {
                "living": {"current_temp": 21.5, "target_temp": 22.0}
            }
        }
        self.mock_controller.get_status.return_value = mock_status
        
        self.interface._update_sensors({})
        
        # Verify controller status was requested
        self.mock_controller.get_status.assert_called_once()
        
        # Verify sensors were updated
        self.assertEqual(self.interface.set_state.call_count, 4)

    def test_update_sensors_no_controller(self):
        """Test sensor updates when controller is not available"""
        self.interface.controller = None
        
        # Should not raise exception
        self.interface._update_sensors({})
        
        # Verify no sensor updates were made
        self.interface.set_state.assert_not_called()

    def test_update_sensors_exception_handling(self):
        """Test sensor update error handling"""
        # Mock controller to raise exception
        self.mock_controller.get_status.side_effect = Exception("Test error")
        
        # Should not raise exception
        self.interface._update_sensors({})
        
        # Verify error was logged
        self.interface.log.assert_called_with(
            "Error updating sensors: Test error",
            level="ERROR"
        )

    def test_find_controller_success(self):
        """Test finding the main controller successfully"""
        mock_app = Mock()
        self.interface.get_app = Mock(return_value=mock_app)
        
        self.interface._find_controller()
        
        # Verify controller was found
        self.assertEqual(self.interface.controller, mock_app)
        self.interface.get_app.assert_called_once_with("smart_aircon_controller")

    def test_find_controller_failure(self):
        """Test handling when main controller is not found"""
        self.interface.get_app = Mock(side_effect=Exception("Not found"))
        
        # Should not raise exception
        self.interface._find_controller()
        
        # Verify controller is None and warning was logged
        self.assertIsNone(self.interface.controller)
        self.interface.log.assert_called_with(
            "Warning: Smart Aircon Controller not found",
            level="WARNING"
        )


class TestIntegrationScenarios(unittest.TestCase):
    """Test integration scenarios between interface and controller"""

    def setUp(self):
        """Set up integration test fixtures"""
        self.interface = SmartAirconControllerInterface()
        self.interface.log = Mock()
        self.interface.register_service = Mock()
        self.interface.set_state = Mock()
        self.interface.run_every = Mock()
        
        # Create a mock controller with realistic behavior
        self.mock_controller = Mock()
        self.mock_controller.config = Mock()
        self.interface.controller = self.mock_controller

    def test_full_enable_disable_cycle(self):
        """Test full enable/disable cycle"""
        # Enable controller
        self.interface._service_toggle("ns", "dom", "svc", {"enabled": True})
        self.mock_controller.toggle_controller.assert_called_with(True)
        
        # Reset mock
        self.mock_controller.reset_mock()
        
        # Disable controller
        self.interface._service_toggle("ns", "dom", "svc", {"enabled": False})
        self.mock_controller.toggle_controller.assert_called_with(False)

    def test_status_and_sensor_consistency(self):
        """Test that status service and sensor updates are consistent"""
        # Mock realistic status
        status = {
            "enabled": True,
            "algorithm_active": True,
            "current_hvac_mode": "heat",
            "active_zones": ["living", "baby_bed"],
            "zone_states": {
                "living": {"current_temp": 21.0, "target_temp": 22.0, "is_active": True},
                "baby_bed": {"current_temp": 19.5, "target_temp": 20.0, "is_active": True}
            }
        }
        self.mock_controller.get_status.return_value = status
        
        # Get status via service
        service_result = self.interface._service_get_status("ns", "dom", "svc", {})
        
        # Update sensors
        self.interface._update_sensors({})
        
        # Verify service and sensors got same data
        self.assertEqual(service_result, status)
        self.assertEqual(self.mock_controller.get_status.call_count, 2)  # Called twice

    def test_temperature_tolerance_update_flow(self):
        """Test temperature tolerance update flow"""
        # Set new tolerance
        new_tolerance = 0.8
        self.interface._service_set_temp_tolerance(
            "ns", "dom", "svc", {"tolerance": new_tolerance}
        )
        
        # Verify config was updated
        self.assertEqual(self.mock_controller.config.temp_tolerance, new_tolerance)


if __name__ == "__main__":
    unittest.main() 