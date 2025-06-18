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
                    "isolation": False
                },
                "baby_bed": {
                    "climate_entity": "climate.baby_bed",
                    "damper_entity": "cover.baby_bed_damper",
                    "isolation": True
                },
                "master_bed": {
                    "climate_entity": "climate.master_bed",
                    "damper_entity": "cover.master_bed_damper",
                    "isolation": False
                }
            }
        }
        
        # Mock entity existence
        self.controller._entity_exists = Mock(return_value=True)
        
        # Initialize the controller
        self.controller._load_config()
        self.controller._initialize_zones()
        self.controller.algorithm_mode = None

    def _mock_zone_states(self, states):
        """Helper to mock climate entity states"""
        def get_state_side_effect(entity_id, attribute=None):
            if attribute == 'all' and entity_id in states:
                return {
                    "state": states[entity_id].get("state", "heat"),
                    "attributes": {
                        "current_temperature": states[entity_id].get("current_temp", 0.0),
                        "temperature": states[entity_id].get("target_temp", 0.0)
                    }
                }
            elif entity_id in states:
                 return states[entity_id].get("state", "heat")
            return None
        self.controller.get_state.side_effect = get_state_side_effect

    def test_config_loading(self):
        """Test configuration loading"""
        self.assertTrue(self.controller.config.enabled)
        self.assertEqual(self.controller.config.check_interval, 30)
        self.assertEqual(self.controller.config.temp_tolerance, 0.5)
        self.assertEqual(self.controller.config.primary_damper_percent, 50)
        self.assertFalse(self.controller.zones["living"].isolation)

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
        mock_states = {
            "climate.living": {"state": "heat", "current_temp": 21.5, "target_temp": 22.0},
            "climate.baby_bed": {"state": "off", "current_temp": 19.2, "target_temp": 20.0},
            "climate.master_bed": {"state": "heat", "current_temp": 20.8, "target_temp": 21.0}
        }
        self._mock_zone_states(mock_states)
        
        self.controller._update_zone_states()
        
        # Check zone states
        self.assertTrue(self.controller.zones["living"].is_active)
        self.assertFalse(self.controller.zones["baby_bed"].is_active)
        self.assertTrue(self.controller.zones["master_bed"].is_active)
        
        self.assertEqual(self.controller.zones["living"].current_temp, 21.5)
        self.assertEqual(self.controller.zones["baby_bed"].current_temp, 19.2)
        self.assertEqual(self.controller.zones["master_bed"].current_temp, 20.8)

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
        
        zones_needing_heating, zones_needing_cooling = self.controller._analyze_zones()
        
        # Both active zones need heating (temp < target - tolerance)
        self.assertIn("living", zones_needing_heating)
        self.assertIn("baby_bed", zones_needing_heating)
        self.assertEqual(len(zones_needing_heating), 2)
        self.assertEqual(len(zones_needing_cooling), 0)

    def test_analyze_zones_cooling_needed(self):
        """Test zone analysis for cooling needs"""
        # Set up zone states
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 23.0
        self.controller.zones["living"].target_temp = 22.0 # Needs cooling
        
        self.controller.zones["baby_bed"].is_active = True
        self.controller.zones["baby_bed"].current_temp = 21.0
        self.controller.zones["baby_bed"].target_temp = 20.0 # Needs cooling
        
        self.controller.zones["master_bed"].is_active = True
        self.controller.zones["master_bed"].current_temp = 20.0
        self.controller.zones["master_bed"].target_temp = 20.0 # Satisfied

        zones_needing_heating, zones_needing_cooling = self.controller._analyze_zones()
        
        self.assertIn("living", zones_needing_cooling)
        self.assertIn("baby_bed", zones_needing_cooling)
        self.assertEqual(len(zones_needing_cooling), 2)
        self.assertEqual(len(zones_needing_heating), 0)

    def test_analyze_zones_no_action_needed(self):
        """Test zone analysis when no heating or cooling is needed"""
        # Set up zone states within tolerance
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 22.0
        self.controller.zones["living"].target_temp = 22.0
        
        zones_needing_heating, zones_needing_cooling = self.controller._analyze_zones()
        
        # No zones need action
        self.assertEqual(len(zones_needing_heating), 0)
        self.assertEqual(len(zones_needing_cooling), 0)

    def test_calculate_damper_positions_heating(self):
        """Test damper position calculation for heating mode"""
        # Set up zones
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 21.0 # Needs heat
        self.controller.zones["living"].target_temp = 22.0
        
        self.controller.zones["baby_bed"].is_active = True
        self.controller.zones["baby_bed"].current_temp = 19.8 # Satisfied, but can benefit
        self.controller.zones["baby_bed"].target_temp = 20.0
        
        self.controller.zones["master_bed"].is_active = True
        self.controller.zones["master_bed"].current_temp = 20.6 # Over temp
        self.controller.zones["master_bed"].target_temp = 20.0
        
        trigger_zones = ["living"]
        positions = self.controller._calculate_damper_positions(trigger_zones, HVACMode.HEAT)
        
        # Check primary zone gets primary opening
        self.assertEqual(positions["living"], 50)
        
        # Check isolated zone (baby_bed) gets 0
        self.assertEqual(positions["baby_bed"], 0)
        
        # Check zone above target gets no opening
        self.assertEqual(positions["master_bed"], 0)

    def test_calculate_damper_positions_cooling(self):
        """Test damper position calculation for cooling mode"""
        # Set up zones
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 23.0 # Needs cooling
        self.controller.zones["living"].target_temp = 22.0
        
        self.controller.zones["master_bed"].is_active = True
        self.controller.zones["master_bed"].current_temp = 20.2 # Can benefit from cooling
        self.controller.zones["master_bed"].target_temp = 20.0

        self.controller.zones["baby_bed"].is_active = True
        self.controller.zones["baby_bed"].current_temp = 19.4 # Under temp
        self.controller.zones["baby_bed"].target_temp = 20.0
        
        trigger_zones = ["living"]
        positions = self.controller._calculate_damper_positions(trigger_zones, HVACMode.COOL)
        
        # Check primary zone gets primary opening
        self.assertEqual(positions["living"], 50)

        # Check secondary zone that can benefit from cooling
        self.assertEqual(positions["master_bed"], 40)
        
        # Check isolated zone (baby_bed) under temp gets 0
        self.assertEqual(positions["baby_bed"], 0)

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
        positions = self.controller._calculate_damper_positions(trigger_zones, HVACMode.HEAT)
        
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
        positions = self.controller._calculate_damper_positions(trigger_zones, HVACMode.HEAT)
        
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

    def test_all_zones_satisfied_heating_true(self):
        """Test all zones satisfied for heating mode"""
        self.controller.algorithm_mode = HVACMode.HEAT
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 22.2
        self.controller.zones["living"].target_temp = 22.0
        
        self.assertTrue(self.controller._all_zones_satisfied())

    def test_all_zones_satisfied_heating_false(self):
        """Test all zones not satisfied for heating mode"""
        self.controller.algorithm_mode = HVACMode.HEAT
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 21.8 # Below target
        self.controller.zones["living"].target_temp = 22.0
        
        self.assertFalse(self.controller._all_zones_satisfied())

    def test_all_zones_satisfied_cooling_true(self):
        """Test all zones satisfied for cooling mode"""
        self.controller.algorithm_mode = HVACMode.COOL
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 21.8
        self.controller.zones["living"].target_temp = 22.0
        
        self.assertTrue(self.controller._all_zones_satisfied())

    def test_all_zones_satisfied_cooling_false(self):
        """Test all zones not satisfied for cooling mode"""
        self.controller.algorithm_mode = HVACMode.COOL
        self.controller.zones["living"].is_active = True
        self.controller.zones["living"].current_temp = 22.2 # Above target
        self.controller.zones["living"].target_temp = 22.0
        
        self.assertFalse(self.controller._all_zones_satisfied())

    def test_execute_smart_algorithm(self):
        """Test the main algorithm execution function"""
        trigger_zones = ["living"]
        with patch.object(self.controller, '_calculate_damper_positions') as mock_calc, \
             patch.object(self.controller, '_set_hvac_mode') as mock_set_mode, \
             patch.object(self.controller, '_apply_damper_positions') as mock_apply:
            
            self.controller._execute_smart_algorithm(trigger_zones, HVACMode.HEAT)
            
            mock_calc.assert_called_with(trigger_zones, HVACMode.HEAT)
            mock_set_mode.assert_called_with(HVACMode.HEAT)
            mock_apply.assert_called()
            self.assertTrue(self.controller.algorithm_active)
            self.assertEqual(self.controller.algorithm_mode, HVACMode.HEAT)

    def test_deactivate_algorithm(self):
        """Test algorithm deactivation"""
        self.controller.algorithm_active = True
        self.controller._set_hvac_mode = Mock()
        
        self.controller._deactivate_algorithm()
        
        # Verify HVAC set to DRY mode
        self.controller._set_hvac_mode.assert_called_once_with(HVACMode.DRY)
        
        # Verify algorithm marked as inactive
        self.assertFalse(self.controller.algorithm_active)
        self.assertIsNone(self.controller.algorithm_mode)

    def test_periodic_check_no_action_needed(self):
        """Test periodic check when no action is needed"""
        with patch.object(self.controller, '_update_zone_states'), \
             patch.object(self.controller, '_analyze_zones', return_value=([], [])) as mock_analyze, \
             patch.object(self.controller, '_execute_smart_algorithm') as mock_execute:
            
            self.controller._periodic_check({})
            mock_analyze.assert_called()
            mock_execute.assert_not_called()

    def test_periodic_check_heating_needed(self):
        """Test periodic check when heating action is needed"""
        zones = ["living"]
        with patch.object(self.controller, '_update_zone_states'), \
             patch.object(self.controller, '_analyze_zones', return_value=(zones, [])) as mock_analyze, \
             patch.object(self.controller, '_execute_smart_algorithm') as mock_execute:

            self.controller._periodic_check({})
            mock_analyze.assert_called()
            mock_execute.assert_called_with(zones, HVACMode.HEAT)

    def test_periodic_check_cooling_needed(self):
        """Test periodic check when cooling action is needed"""
        zones = ["living"]
        with patch.object(self.controller, '_update_zone_states'), \
             patch.object(self.controller, '_analyze_zones', return_value=([], zones)) as mock_analyze, \
             patch.object(self.controller, '_execute_smart_algorithm') as mock_execute:

            self.controller._periodic_check({})
            mock_analyze.assert_called()
            mock_execute.assert_called_with(zones, HVACMode.COOL)

    def test_periodic_check_deactivation(self):
        """Test periodic check for deactivation"""
        self.controller._update_zone_states = Mock()
        self.controller._analyze_zones = Mock(return_value=([], []))
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
        self.assertIsNone(self.controller.algorithm_mode)

    def test_toggle_controller_disable_with_active_algorithm(self):
        """Test disabling controller with active algorithm"""
        self.controller.config.enabled = True
        self.controller.algorithm_active = True
        self.controller._deactivate_algorithm = Mock()
        
        self.controller.toggle_controller(False)
        
        self.assertFalse(self.controller.config.enabled)
        self.controller._deactivate_algorithm.assert_called_once()
        self.assertIsNone(self.controller.algorithm_mode)

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

    def test_periodic_check_sticks_to_mode_during_conflict(self):
        """Test that periodic check does not switch modes mid-cycle."""
        self.controller.algorithm_active = True
        self.controller.algorithm_mode = HVACMode.HEAT

        # One zone still needs heating, but another now needs cooling (a new conflict)
        zones_needing_heating = ["living"]
        zones_needing_cooling = ["master_bed"]

        with patch.object(self.controller, '_update_zone_states'), \
             patch.object(self.controller, '_analyze_zones', return_value=(zones_needing_heating, zones_needing_cooling)), \
             patch.object(self.controller, '_all_zones_satisfied', return_value=False), \
             patch.object(self.controller, '_deactivate_algorithm') as mock_deactivate, \
             patch.object(self.controller, '_execute_smart_algorithm') as mock_execute:

            self.controller._periodic_check({})

            # It should NOT deactivate
            mock_deactivate.assert_not_called()
            # It SHOULD call execute again, but ONLY for the original HEAT mode
            mock_execute.assert_called_with(zones_needing_heating, HVACMode.HEAT)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""

    def setUp(self):
        """Set up test fixtures"""
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
                "living": {
                    "climate_entity": "climate.living",
                    "damper_entity": "cover.living_damper"
                }
            }
        }
        
        self.controller._load_config()
        self.controller._initialize_zones()

    def test_unavailable_climate_entity_state(self):
        """Test handling of unavailable climate entity state"""
        mock_states = {"climate.living": {"state": "unavailable"}}
        self._mock_zone_states(mock_states)
        self.controller._update_zone_states()
        self.assertFalse(self.controller.zones["living"].is_active)

    def test_invalid_temperature_value(self):
        """Test handling of invalid temperature value"""
        mock_states = {"climate.living": {"current_temp": "invalid"}}
        self._mock_zone_states(mock_states)
        self.controller._update_zone_states()
        self.assertEqual(self.controller.zones["living"].current_temp, 0.0) # Should not crash and default to 0
        self.controller.log.assert_called()

    def test_damper_service_call_failure(self):
        """Test handling of damper service call failures"""
        self.controller.call_service.side_effect = Exception("Service call failed")
        
        positions = {"living": 50}
        
        # Should not raise exception
        self.controller._apply_damper_positions(positions)
        
        # Error should be logged - note the exact call
        args_list = [call[0] for call in self.controller.log.call_args_list]
        error_logged = any("Error setting damper for living" in str(args) for args in args_list)
        self.assertTrue(error_logged, f"Expected error log not found. Actual calls: {self.controller.log.call_args_list}")

    def test_hvac_mode_change_failure(self):
        """Test handling of HVAC mode change failures"""
        self.controller.get_state.return_value = "dry"
        self.controller.call_service.side_effect = Exception("Service call failed")
        self.controller._set_hvac_mode(HVACMode.HEAT)
        self.controller.log.assert_called_with("Error setting HVAC mode: Service call failed", level="ERROR")


if __name__ == "__main__":
    unittest.main() 