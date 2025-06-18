import unittest
from unittest.mock import Mock, patch, MagicMock
import datetime
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
from smart_aircon_controller import SmartAirconController, ZoneState, ControllerConfig, HVACMode


class TestSmartAirconController(unittest.TestCase):
    """Test cases for the Smart Aircon Controller"""

    def setUp(self):
        """Set up test fixtures"""        
        # Create controller instance with mocked dependencies
        self.controller = SmartAirconController()
        self.controller.log = Mock()
        self.controller.get_state = Mock()
        self.controller.call_service = Mock()
        self.controller.run_every = Mock()
        self.controller.get_app = Mock()
        self.controller.set_state = Mock()
        self.controller.register_service = Mock()
        
        # Mock configuration
        self.controller.args = {
            "enabled": True,
            "check_interval": 30,
            "temp_tolerance": 0.5,
            "main_climate": "climate.aircon",
            "primary_damper_percent": 50,
            "secondary_damper_percent": 40,
            "overflow_damper_percent": 10,
            "zones": {
                "living": {
                    "climate_entity": "climate.living",
                    "damper_entity": "cover.living_damper",
                    "temp_sensor": "sensor.living_temperature",
                    "isolation": False
                },
                "baby_bed": {
                    "climate_entity": "climate.baby_bed",
                    "damper_entity": "cover.baby_bed_damper",
                    "temp_sensor": "sensor.baby_bed_temperature",
                    "isolation": True
                },
                "master_bed": {
                    "climate_entity": "climate.master_bed",
                    "damper_entity": "cover.master_bed_damper",
                    "temp_sensor": "sensor.master_bed_temperature",
                    "isolation": False
                }
            }
        }
        
        # Mock entity existence
        self.controller._entity_exists = Mock(return_value=True)
        
        # Initialize the controller
        self.controller._load_config()
        self.controller._initialize_zones()

    def test_config_loading(self):
        """Test configuration loading"""
        self.assertTrue(self.controller.config.enabled)
        self.assertEqual(self.controller.config.check_interval, 30)
        self.assertEqual(self.controller.config.temp_tolerance, 0.5)
        self.assertEqual(self.controller.config.primary_damper_percent, 50)

    def test_zone_initialization(self):
        """Test zone initialization"""
        self.assertEqual(len(self.controller.zones), 3)
        self.assertIn("living", self.controller.zones)
        self.assertIn("baby_bed", self.controller.zones)
        self.assertIn("master_bed", self.controller.zones)
        
        # Check baby room isolation
        self.assertTrue(self.controller.zones["baby_bed"].isolation)
        self.assertFalse(self.controller.zones["living"].isolation)

    def test_zone_state_update(self):
        """Test zone state updating"""
        # Mock climate entity states
        self.controller.get_state.side_effect = lambda entity, attribute=None: {
            "climate.living": "heat",
            "climate.baby_bed": "off",
            "climate.master_bed": "heat",
            "sensor.living_temperature": "21.5",
            "sensor.baby_bed_temperature": "19.2",
            "sensor.master_bed_temperature": "20.8"
        }.get(entity, {
            "attributes": {"temperature": 22.0}
        } if attribute == "all" else 50)
        
        self.controller._update_zone_states()
        
        # Check zone states
        self.assertTrue(self.controller.zones["living"].is_active)
        self.assertFalse(self.controller.zones["baby_bed"].is_active)
        self.assertTrue(self.controller.zones["master_bed"].is_active)
        
        self.assertEqual(self.controller.zones["living"].current_temp, 21.5)
        self.assertEqual(self.controller.zones["baby_bed"].current_temp, 19.2)

    def test_analyze_zones_heating_needed(self):
        """Test zone analysis for heating needs"""
        # Set up zone states
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 21.0
        self.controller.zones["living"].target_temp = 22.0
        
        self.controller.zones["baby_bed"].is_active = True
        self.controller.zones["baby_bed"].current_temp = 19.0
        self.controller.zones["baby_bed"].target_temp = 20.0
        
        self.controller.zones["master_bed"].is_active = False
        
        zones_needing_action = self.controller._analyze_zones()
        
        # Both active zones need heating (temp < target - tolerance)
        self.assertIn("living", zones_needing_action)
        self.assertIn("baby_bed", zones_needing_action)
        self.assertEqual(len(zones_needing_action), 2)

    def test_analyze_zones_no_heating_needed(self):
        """Test zone analysis when no heating is needed"""
        # Set up zone states within tolerance
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 22.0
        self.controller.zones["living"].target_temp = 22.0
        
        zones_needing_action = self.controller._analyze_zones()
        
        # No zones need heating
        self.assertEqual(len(zones_needing_action), 0)

    def test_calculate_damper_positions_primary_zone(self):
        """Test damper position calculation for primary trigger zone"""
        # Set up zones
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 21.0
        self.controller.zones["living"].target_temp = 22.0
        
        self.controller.zones["baby_bed"].is_active = True
        self.controller.zones["baby_bed"].current_temp = 19.8
        self.controller.zones["baby_bed"].target_temp = 20.0
        
        self.controller.zones["master_bed"].is_active = True
        self.controller.zones["master_bed"].current_temp = 20.5
        self.controller.zones["master_bed"].target_temp = 20.0
        
        trigger_zones = ["living"]
        positions = self.controller._calculate_damper_positions(trigger_zones)
        
        # Check primary zone gets full opening
        self.assertEqual(positions["living"], 50)
        
        # Check secondary zone that could benefit - NOTE: Baby bed is isolated so gets 0
        self.assertEqual(positions["baby_bed"], 0)
        
        # Check zone above target gets minimal opening
        self.assertEqual(positions["master_bed"], 10)

    def test_calculate_damper_positions_isolated_zone(self):
        """Test damper position calculation with isolated zone"""
        # Set up zones
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 21.0
        self.controller.zones["living"].target_temp = 22.0
        
        self.controller.zones["baby_bed"].is_active = True
        self.controller.zones["baby_bed"].current_temp = 19.0
        self.controller.zones["baby_bed"].target_temp = 20.0
        
        # Living room triggers, baby bed is isolated
        trigger_zones = ["living"]
        positions = self.controller._calculate_damper_positions(trigger_zones)
        
        # Baby bed should not participate in shared heating
        self.assertEqual(positions["baby_bed"], 0)
        self.assertEqual(positions["living"], 50)

    def test_calculate_damper_positions_baby_bed_trigger(self):
        """Test damper position calculation when baby bed is the trigger"""
        # Set up zones
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 21.8
        self.controller.zones["living"].target_temp = 22.0
        
        self.controller.zones["baby_bed"].is_active = True
        self.controller.zones["baby_bed"].current_temp = 19.0
        self.controller.zones["baby_bed"].target_temp = 20.0
        
        # Baby bed triggers - should get primary opening despite isolation
        trigger_zones = ["baby_bed"]
        positions = self.controller._calculate_damper_positions(trigger_zones)
        
        # Baby bed gets primary opening as it's the trigger
        self.assertEqual(positions["baby_bed"], 50)
        
        # Living room gets secondary opening
        self.assertEqual(positions["living"], 40)

    def test_apply_damper_positions(self):
        """Test applying damper positions"""
        positions = {
            "living": 50,
            "baby_bed": 0,
            "master_bed": 40
        }
        
        self.controller._apply_damper_positions(positions)
        
        # Check that service calls were made
        self.assertEqual(self.controller.call_service.call_count, 3)

    def test_set_hvac_mode(self):
        """Test HVAC mode setting"""
        # Mock current mode different from target
        self.controller.get_state.return_value = "dry"
        
        self.controller._set_hvac_mode(HVACMode.HEAT)
        
        # Verify service call
        self.controller.call_service.assert_called_with(
            "climate/set_hvac_mode",
            entity_id="climate.aircon",
            hvac_mode="heat"
        )
        
        # Verify mode tracking
        self.assertEqual(self.controller.current_hvac_mode, "heat")

    def test_set_hvac_mode_no_change_needed(self):
        """Test HVAC mode setting when no change is needed"""
        # Mock current mode same as target
        self.controller.get_state.return_value = "heat"
        
        self.controller._set_hvac_mode(HVACMode.HEAT)
        
        # Verify no service call made
        self.controller.call_service.assert_not_called()

    def test_all_zones_satisfied_true(self):
        """Test all zones satisfied check - positive case"""
        # Set up zones within tolerance
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 22.0
        self.controller.zones["living"].target_temp = 22.0
        
        self.controller.zones["baby_bed"].is_active = True
        self.controller.zones["baby_bed"].current_temp = 20.2
        self.controller.zones["baby_bed"].target_temp = 20.0
        
        self.controller.zones["master_bed"].is_active = False
        
        result = self.controller._all_zones_satisfied()
        self.assertTrue(result)

    def test_all_zones_satisfied_false(self):
        """Test all zones satisfied check - negative case"""
        # Set up zones with one outside tolerance
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 21.0
        self.controller.zones["living"].target_temp = 22.0
        
        self.controller.zones["baby_bed"].is_active = True
        self.controller.zones["baby_bed"].current_temp = 20.2
        self.controller.zones["baby_bed"].target_temp = 20.0
        
        result = self.controller._all_zones_satisfied()
        self.assertFalse(result)

    def test_execute_smart_algorithm(self):
        """Test smart algorithm execution"""
        trigger_zones = ["living"]
        
        # Mock the sub-methods
        self.controller._calculate_damper_positions = Mock(return_value={"living": 50})
        self.controller._set_hvac_mode = Mock()
        self.controller._apply_damper_positions = Mock()
        
        self.controller._execute_smart_algorithm(trigger_zones)
        
        # Verify all steps were called
        self.controller._calculate_damper_positions.assert_called_once_with(trigger_zones)
        self.controller._set_hvac_mode.assert_called_once_with(HVACMode.HEAT)
        self.controller._apply_damper_positions.assert_called_once()
        
        # Verify algorithm is marked as active
        self.assertTrue(self.controller.algorithm_active)

    def test_deactivate_algorithm(self):
        """Test algorithm deactivation"""
        self.controller.algorithm_active = True
        self.controller._set_hvac_mode = Mock()
        
        self.controller._deactivate_algorithm()
        
        # Verify HVAC set to DRY mode
        self.controller._set_hvac_mode.assert_called_once_with(HVACMode.DRY)
        
        # Verify algorithm marked as inactive
        self.assertFalse(self.controller.algorithm_active)

    def test_periodic_check_no_action_needed(self):
        """Test periodic check when no action is needed"""
        self.controller._update_zone_states = Mock()
        self.controller._analyze_zones = Mock(return_value=[])
        self.controller.algorithm_active = False
        
        self.controller._periodic_check({})
        
        # Verify zone states were updated
        self.controller._update_zone_states.assert_called_once()
        
        # Verify analysis was performed
        self.controller._analyze_zones.assert_called_once()

    def test_periodic_check_action_needed(self):
        """Test periodic check when action is needed"""
        self.controller._update_zone_states = Mock()
        self.controller._analyze_zones = Mock(return_value=["living"])
        self.controller._execute_smart_algorithm = Mock()
        
        self.controller._periodic_check({})
        
        # Verify algorithm was executed
        self.controller._execute_smart_algorithm.assert_called_once_with(["living"])

    def test_periodic_check_deactivation(self):
        """Test periodic check triggering deactivation"""
        self.controller._update_zone_states = Mock()
        self.controller._analyze_zones = Mock(return_value=[])
        self.controller._all_zones_satisfied = Mock(return_value=True)
        self.controller._deactivate_algorithm = Mock()
        self.controller.algorithm_active = True
        
        self.controller._periodic_check({})
        
        # Verify deactivation was triggered
        self.controller._deactivate_algorithm.assert_called_once()

    def test_toggle_controller_enable(self):
        """Test enabling the controller"""
        self.controller.config.enabled = False
        
        self.controller.toggle_controller(True)
        
        self.assertTrue(self.controller.config.enabled)

    def test_toggle_controller_disable_with_active_algorithm(self):
        """Test disabling controller with active algorithm"""
        self.controller.config.enabled = True
        self.controller.algorithm_active = True
        self.controller._deactivate_algorithm = Mock()
        
        self.controller.toggle_controller(False)
        
        self.assertFalse(self.controller.config.enabled)
        self.controller._deactivate_algorithm.assert_called_once()

    def test_get_status(self):
        """Test status reporting"""
        # Set up some state
        self.controller.config.enabled = True
        self.controller.algorithm_active = True
        self.controller.current_hvac_mode = "heat"
        self.controller.last_check_time = datetime.datetime(2023, 1, 1, 12, 0, 0)
        
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 21.5
        self.controller.zones["living"].target_temp = 22.0
        
        status = self.controller.get_status()
        
        # Verify status structure
        self.assertTrue(status["enabled"])
        self.assertTrue(status["algorithm_active"])
        self.assertEqual(status["current_hvac_mode"], "heat")
        self.assertIn("living", status["active_zones"])
        self.assertEqual(status["zone_states"]["living"]["current_temp"], 21.5)

    def test_entity_exists(self):
        """Test entity existence checking"""
        # Mock successful entity check
        self.controller.get_state = Mock(return_value="some_state")
        self.assertTrue(self.controller._entity_exists("climate.test"))
        
        # Mock failed entity check
        self.controller.get_state = Mock(return_value=None)
        self.assertFalse(self.controller._entity_exists("climate.nonexistent"))
        
        # Mock exception during check
        self.controller.get_state = Mock(side_effect=Exception("Error"))
        self.assertFalse(self.controller._entity_exists("climate.error"))

    def test_error_handling_in_periodic_check(self):
        """Test error handling in periodic check"""
        # Mock an exception in zone analysis
        self.controller._update_zone_states = Mock(side_effect=Exception("Test error"))
        
        # Should not raise exception
        self.controller._periodic_check({})
        
        # Verify error was logged
        self.controller.log.assert_called_with(
            "Error in periodic check: Test error",
            level="ERROR"
        )


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""

    def setUp(self):
        """Set up test fixtures for edge cases"""
        self.controller = SmartAirconController()
        self.controller.log = Mock()
        self.controller.get_state = Mock()
        self.controller.call_service = Mock()
        self.controller.run_every = Mock()
        self.controller._entity_exists = Mock(return_value=True)
        
        # Basic configuration
        self.controller.args = {
            "enabled": True,
            "zones": {
                "test_zone": {
                    "climate_entity": "climate.test",
                    "damper_entity": "cover.test_damper",
                    "temp_sensor": "sensor.test_temp",
                    "isolation": False
                }
            }
        }
        
        self.controller._load_config()
        self.controller._initialize_zones()

    def test_unavailable_climate_entity(self):
        """Test handling of unavailable climate entity"""
        self.controller.get_state.return_value = "unavailable"
        
        self.controller._update_zone_states()
        
        # Zone should remain inactive
        self.assertFalse(self.controller.zones["test_zone"].is_active)

    def test_unavailable_temperature_sensor(self):
        """Test handling of unavailable temperature sensor"""
        def mock_get_state(entity, attribute=None):
            if "temp" in entity:
                return "unavailable"
            return "heat"
        
        self.controller.get_state.side_effect = mock_get_state
        
        self.controller._update_zone_states()
        
        # Temperature should remain at default
        self.assertEqual(self.controller.zones["test_zone"].current_temp, 0.0)

    def test_invalid_temperature_value(self):
        """Test handling of invalid temperature values"""
        def mock_get_state(entity, attribute=None):
            if "temp" in entity:
                return "not_a_number"
            return "heat"
        
        self.controller.get_state.side_effect = mock_get_state
        
        # Should not raise exception
        self.controller._update_zone_states()

    def test_damper_service_call_failure(self):
        """Test handling of damper service call failures"""
        self.controller.call_service.side_effect = Exception("Service call failed")
        
        positions = {"test_zone": 50}
        
        # Should not raise exception
        self.controller._apply_damper_positions(positions)
        
        # Error should be logged - note the exact call
        args_list = [call[0] for call in self.controller.log.call_args_list]
        error_logged = any("Error setting damper for test_zone" in str(args) for args in args_list)
        self.assertTrue(error_logged, f"Expected error log not found. Actual calls: {self.controller.log.call_args_list}")

    def test_hvac_mode_change_failure(self):
        """Test handling of HVAC mode change failures"""
        self.controller.call_service.side_effect = Exception("HVAC error")
        self.controller.get_state.return_value = "dry"
        
        # Should not raise exception
        self.controller._set_hvac_mode(HVACMode.HEAT)
        
        # Error should be logged
        args_list = [call[0] for call in self.controller.log.call_args_list]
        error_logged = any("Error setting HVAC mode" in str(args) for args in args_list)
        self.assertTrue(error_logged, f"Expected error log not found. Actual calls: {self.controller.log.call_args_list}")


if __name__ == "__main__":
    unittest.main() 