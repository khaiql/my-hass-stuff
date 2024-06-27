import unittest
from unittest.mock import MagicMock, Mock, patch
from ac_controller import AirconController, Zone, SwitchesManager

class TestAirconController(unittest.TestCase):
    @patch.object(AirconController, '__init__', lambda x: None)
    def setUp(self):
        self.mock_adapi = MagicMock()

        # Mock the initialization of the zones
        self.bedroom_zone = Zone(self.mock_adapi, 'bedroom', config={'priority': 1, 'temperature_entity_id': 1, 'switch_entity_id': 'bedroom_switch', 'state_entity_id': 3})
        self.kitchen_zone = Zone(self.mock_adapi, 'kitchen', config={'priority': 2, 'temperature_entity_id': 1, 'switch_entity_id': 'kitchen_switch', 'state_entity_id': 3})
        self.study_zone = Zone(self.mock_adapi, 'study', config={'priority': 1, 'temperature_entity_id': 1, 'switch_entity_id': 'study_switch', 'state_entity_id': 3})

        # Create a mock AirconController instance
        self.mock_hass = AirconController()
        self.mock_hass.log = MagicMock(return_value=None)
        self.mock_hass.zones = [self.bedroom_zone, self.kitchen_zone, self.study_zone]
        self.mock_hass.get_desired_temperature = MagicMock(return_value=20)
        self.mock_hass.get_trigger_threshold = MagicMock(return_value=0.5)
        self.mock_hass.get_mode = MagicMock(return_value='heating')
        self.mock_hass.get_power_on_strategy = MagicMock(return_value='all')

        self.mock_hass.power_switch = MagicMock()
        self.mock_hass.active_zones = MagicMock()

    def test_zone_groups(self):
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.study_zone, self.kitchen_zone]

        # Run the zone_groups method
        result = self.mock_hass.zone_groups()

        # Check the expected result
        expected_result = [[self.bedroom_zone, self.study_zone], [self.kitchen_zone]]
        self.assertEqual(result, expected_result)

    def test_determine_power_state_with_power_switch_on_and_reached_desired_temp(self):
        self.mock_hass.power_switch.get_state = MagicMock(return_value='on')
        self.mock_hass.active_zones.return_value = [self.bedroom_zone]
        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=True)

        self.assertEqual(self.mock_hass.determine_power_state(), 'off')

    def test_determine_power_state_with_power_switch_on_and_has_not_reached_desired_temp(self):
        self.mock_hass.power_switch.get_state = MagicMock(return_value='on')
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.study_zone]
        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=False)
        self.study_zone.has_reached_desired_temp = MagicMock(return_value=True)

        self.assertEqual(self.mock_hass.determine_power_state(), 'on')

    def test_determine_power_state_with_power_switch_off_and_strategy_all_scenario1(self):
        self.mock_hass.power_on_strategy = 'all'
        self.mock_hass.power_switch.get_state = MagicMock(return_value='off')
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.study_zone]
        self.bedroom_zone.is_out_of_desired_temp = MagicMock(return_value=True)
        self.study_zone.is_out_of_desired_temp = MagicMock(return_value=True)

        self.assertEqual(self.mock_hass.determine_power_state(), 'on')

    def test_determine_power_state_with_power_switch_off_and_strategy_all_scenario2(self):
        self.mock_hass.power_on_strategy = 'all'
        self.mock_hass.power_switch.get_state = MagicMock(return_value='off')
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.study_zone]
        self.bedroom_zone.is_out_of_desired_temp = MagicMock(return_value=False)
        self.study_zone.is_out_of_desired_temp = MagicMock(return_value=True)

        self.assertEqual(self.mock_hass.determine_power_state(), 'off')

    def test_determine_power_state_with_power_switch_off_and_strategy_at_least_one(self):
        self.mock_hass.get_power_on_strategy = MagicMock(return_value='at_least_one')
        self.mock_hass.power_switch.get_state = MagicMock(return_value='off')
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.study_zone]
        self.bedroom_zone.is_out_of_desired_temp = MagicMock(return_value=False)
        self.study_zone.is_out_of_desired_temp = MagicMock(return_value=True)

        self.assertEqual(self.mock_hass.determine_power_state(), 'on')

    def test_determine_switch_states_with_two_zones_and_bedroom_zone_isnt_good_and_bedroom_is_running(self):
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.kitchen_zone]

        self.bedroom_zone.is_running = MagicMock(return_value=True)
        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=False)
        self.kitchen_zone.has_reached_desired_temp = MagicMock(return_value=False)

        result = self.mock_hass.determine_zone_switch_states()
        expected = {'bedroom': 'on', 'kitchen': 'off'}
        self.assertEqual(result, expected)

    def test_determine_switch_states_with_two_zones_and_bedroom_zone_is_cool_and_is_running(self):
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.kitchen_zone]

        self.bedroom_zone.is_running = MagicMock(return_value=True)
        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=True)
        self.kitchen_zone.has_reached_desired_temp = MagicMock(return_value=False)

        result = self.mock_hass.determine_zone_switch_states()
        expected = {'bedroom': 'off', 'kitchen': 'on'}
        self.assertEqual(result, expected)

    def test_determine_switch_states_with_three_zones_and_bedroom_zone_is_good_and_not_running(self):
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.study_zone, self.kitchen_zone]

        self.bedroom_zone.is_running = MagicMock(return_value=False)
        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=True)
        self.bedroom_zone.is_out_of_desired_temp = MagicMock(return_value=False)
        self.kitchen_zone.has_reached_desired_temp = MagicMock(return_value=False)
        self.study_zone.has_reached_desired_temp = MagicMock(return_value=False)
        self.study_zone.is_running = MagicMock(return_value=True)

        result = self.mock_hass.determine_zone_switch_states()
        expected = {'bedroom': 'off', 'kitchen': 'off', 'study': 'on'}
        self.assertEqual(result, expected)

    def test_determine_switch_states_with_two_zones_and_bedroom_zone_is_not_out_of_range_and_is_not_running(self):
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.kitchen_zone]

        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=False)
        self.bedroom_zone.is_out_of_desired_temp = MagicMock(return_value=False)
        self.bedroom_zone.is_running = MagicMock(return_value=False)
        self.kitchen_zone.has_reached_desired_temp = MagicMock(return_value=False)

        result = self.mock_hass.determine_zone_switch_states()
        expected = {'bedroom': 'off', 'kitchen': 'on'}
        self.assertEqual(result, expected)

    def test_determine_switch_states_with_kitchen_and_bedroom_and_bedroom_is_out_of_range_and_kitchen_is_running(self):
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.kitchen_zone]

        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=False)
        self.bedroom_zone.is_out_of_desired_temp = MagicMock(return_value=True)
        self.bedroom_zone.is_running = MagicMock(return_value=False)
        self.bedroom_zone.is_running = MagicMock(return_value=True)
        self.kitchen_zone.has_reached_desired_temp = MagicMock(return_value=False)

        result = self.mock_hass.determine_zone_switch_states()
        expected = {'bedroom': 'on', 'kitchen': 'off'}
        self.assertEqual(result, expected)


    @patch('__main__.SwitchesManager')
    def test_smart_control_bedroom_is_active_and_not_cool(self, MockSwitchesManager):
        self.mock_hass.active_zones.return_value = [self.bedroom_zone]
        self.mock_hass.power_switch.get_state = MagicMock(return_value='off')
        mock_switches_manager = MockSwitchesManager()
        self.mock_hass.switches_manager = mock_switches_manager

        self.bedroom_zone.is_out_of_desired_temp = MagicMock(return_value=True)
        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=False)
        self.mock_hass.power_switch.toggle = Mock(return_value=None)

        self.mock_hass.smart_control('test_entity', {}, 'on', 'off')

        self.mock_hass.power_switch.toggle.assert_called_once()
        mock_switches_manager.update_states.assert_called_with(bedroom='on')

    @patch('__main__.SwitchesManager')
    def test_smart_control_bedroom_is_active_and_is_cool(self, MockSwitchesManager):
        self.mock_hass.active_zones.return_value = [self.bedroom_zone]
        self.mock_hass.power_switch.get_state = MagicMock(return_value='off')
        mock_switches_manager = MockSwitchesManager()
        self.mock_hass.switches_manager = mock_switches_manager

        self.bedroom_zone.is_out_of_desired_temp = MagicMock(return_value=False)
        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=False)
        self.mock_hass.power_switch.toggle = Mock(return_value=None)

        self.mock_hass.smart_control('test_entity', {}, 'on', 'off')

        self.mock_hass.power_switch.toggle.assert_not_called()

    @patch('__main__.SwitchesManager')
    def test_smart_control_all_zones_are_off(self, MockSwitchesManager):
        self.mock_hass.active_zones.return_value = [self.bedroom_zone]
        self.mock_hass.power_switch.get_state = MagicMock(return_value='on')
        mock_switches_manager = MockSwitchesManager()
        self.mock_hass.switches_manager = mock_switches_manager
        self.mock_hass.determine_power_state = MagicMock(return_value='on')

        self.bedroom_zone.is_out_of_desired_temp = MagicMock(return_value=False)
        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=True)
        self.mock_hass.power_switch.toggle = Mock(return_value=None)

        self.mock_hass.smart_control('test_entity', {}, 'on', 'off')

        self.mock_hass.power_switch.toggle.assert_called_once()
        mock_switches_manager.update_states.assert_not_called()

    @patch('__main__.SwitchesManager')
    def test_smart_control_with_trigger_zone(self, MockSwitchesManager):
        self.mock_hass.active_zones.return_value = [self.bedroom_zone, self.kitchen_zone]
        self.mock_hass.power_switch.get_state = MagicMock(return_value='off')
        mock_switches_manager = MockSwitchesManager()
        self.mock_hass.switches_manager = mock_switches_manager
        self.mock_hass.determine_power_state = MagicMock(return_value='on')
        self.mock_hass.power_switch.toggle = Mock(return_value=None)

        self.bedroom_zone.is_out_of_desired_temp = MagicMock(return_value=False)
        self.bedroom_zone.has_reached_desired_temp = MagicMock(return_value=False)
        self.kitchen_zone.is_out_of_desired_temp = MagicMock(return_value=True)
        self.kitchen_zone.has_reached_desired_temp = MagicMock(return_value=False)

        self.mock_hass.find_trigger_zone = MagicMock(return_value=self.kitchen_zone)
        self.mock_hass.smart_control('kitchen_switch', {}, 'on', 'off')

        self.mock_hass.power_switch.toggle.assert_called_once()
        self.mock_hass.find_trigger_zone.assert_called_once_with('kitchen_switch')
        mock_switches_manager.update_states.assert_called_with(bedroom='off', kitchen='on')

if __name__ == '__main__':
    unittest.main()
