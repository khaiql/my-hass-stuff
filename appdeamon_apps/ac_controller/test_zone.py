import unittest
from unittest.mock import MagicMock
from ac_controller import Zone

class TestZone(unittest.TestCase):
  def setUp(self):
    self.mock_adapi = MagicMock()
    config = {
      'priority': '1',
      'temperature_entity_id': '1',
      'switch_entity_id': '2',
      'state_entity_id': '3'
    }
    self.mock_zone = Zone(self.mock_adapi, "test_zone", config=config)

  def test_has_reached_desired_temp_with_global_setting(self):
    self.mock_zone.get_current_temperature = MagicMock(return_value=20)
    self.assertTrue(self.mock_zone.has_reached_desired_temp(20))

  def test_has_reached_desired_temp_with_zone_setting(self):
    mock_desired_temp_entity = MagicMock()
    mock_desired_temp_entity.get_state.return_value = 23
    self.mock_zone.desired_temperature_setting_entity = mock_desired_temp_entity
    self.assertFalse(self.mock_zone.has_reached_desired_temp(20))

  def test_is_out_of_desired_temp_with_global_settings(self):
    self.mock_zone.get_current_temperature = MagicMock(return_value=20)
    self.assertTrue(self.mock_zone.is_out_of_desired_temp(22, 1))

  def test_is_out_of_desired_temp_with_zone_settings(self):
    self.mock_zone.get_current_temperature = MagicMock(return_value=20)

    mock_desired_temp_entity = MagicMock()
    mock_desired_temp_entity.get_state.return_value = 22
    self.mock_zone.desired_temperature_setting_entity = mock_desired_temp_entity

    mock_threshold_entity = MagicMock()
    mock_threshold_entity.get_state.return_value = 1
    self.mock_zone.threshold_entity = mock_threshold_entity

    self.assertTrue(self.mock_zone.is_out_of_desired_temp(20, 1))


if __name__ == '__main__':
    unittest.main()