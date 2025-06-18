#!/usr/bin/env python3
"""
Simple test runner for Smart Aircon Controller
"""

import unittest
from unittest.mock import Mock, MagicMock
import sys
import os
import types

# Add the current directory to sys.path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock AppDaemon before importing our modules
class MockHass:
    """Mock AppDaemon Hass class"""
    def __init__(self):
        self.log = Mock()
        self.get_state = Mock()
        self.call_service = Mock()
        self.run_every = Mock()
        self.get_app = Mock()
        self.set_state = Mock()
        self.register_service = Mock()
        self.args = {}

# Create proper module objects instead of MagicMocks
appdaemon_module = types.ModuleType('appdaemon')
plugins_module = types.ModuleType('appdaemon.plugins')
hass_module = types.ModuleType('appdaemon.plugins.hass')
hassapi_module = types.ModuleType('appdaemon.plugins.hass.hassapi')

# Set up the Hass class in the hassapi module
hassapi_module.Hass = MockHass

# Set up the module hierarchy
appdaemon_module.plugins = plugins_module
plugins_module.hass = hass_module
hass_module.hassapi = hassapi_module

# Install in sys.modules
sys.modules['appdaemon'] = appdaemon_module
sys.modules['appdaemon.plugins'] = plugins_module
sys.modules['appdaemon.plugins.hass'] = hass_module
sys.modules['appdaemon.plugins.hass.hassapi'] = hassapi_module

# Now import our modules
from smart_aircon_controller import SmartAirconController, ZoneState, ControllerConfig, HVACMode
from controller_interface import SmartAirconControllerInterface

def test_basic_imports():
    """Test that we can import the modules"""
    print("✓ Imports successful")
    return True

def test_controller_creation():
    """Test that we can create a controller instance"""
    try:
        controller = SmartAirconController()
        print("✓ Controller creation successful")
        return True
    except Exception as e:
        print(f"✗ Controller creation failed: {e}")
        return False

def test_interface_creation():
    """Test that we can create an interface instance"""
    try:
        interface = SmartAirconControllerInterface()
        print("✓ Interface creation successful")
        return True
    except Exception as e:
        print(f"✗ Interface creation failed: {e}")
        return False

def test_controller_config_loading():
    """Test controller configuration loading"""
    try:
        controller = SmartAirconController()
        
        # Mock the dependencies
        controller.log = Mock()
        controller.get_state = Mock()
        controller.call_service = Mock()
        controller.run_every = Mock()
        controller._entity_exists = Mock(return_value=True)
        
        # Mock configuration
        controller.args = {
            "enabled": True,
            "check_interval": 30,
            "temp_tolerance": 0.7,
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
                }
            }
        }
        
        # Load configuration
        controller._load_config()
        
        # Test configuration values
        assert controller.config.enabled == True
        assert controller.config.temp_tolerance == 0.7
        assert controller.config.check_interval == 30
        assert controller.config.primary_damper_percent == 50
        
        print("✓ Controller configuration loading successful")
        return True
    except Exception as e:
        print(f"✗ Controller configuration loading failed: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
        return False

def test_zone_initialization():
    """Test zone initialization"""
    try:
        controller = SmartAirconController()
        
        # Mock the dependencies
        controller.log = Mock()
        controller.get_state = Mock()
        controller.call_service = Mock()
        controller.run_every = Mock()
        controller._entity_exists = Mock(return_value=True)
        
        # Initialize zones dictionary (normally done in initialize())
        controller.zones = {}
        
        # Mock configuration
        controller.args = {
            "enabled": True,
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
                }
            }
        }
        
        # Initialize
        controller._load_config()
        controller._initialize_zones()
        
        # Test zones
        assert len(controller.zones) == 2
        assert "living" in controller.zones
        assert "baby_bed" in controller.zones
        assert controller.zones["baby_bed"].isolation == True
        assert controller.zones["living"].isolation == False
        
        print("✓ Zone initialization successful")
        return True
    except Exception as e:
        print(f"✗ Zone initialization failed: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
        return False

def test_damper_calculation():
    """Test damper position calculation"""
    try:
        controller = SmartAirconController()
        
        # Mock the dependencies
        controller.log = Mock()
        controller.get_state = Mock()
        controller.call_service = Mock()
        controller.run_every = Mock()
        controller._entity_exists = Mock(return_value=True)
        
        # Initialize zones dictionary (normally done in initialize())
        controller.zones = {}
        
        # Mock configuration
        controller.args = {
            "enabled": True,
            "temp_tolerance": 0.5,
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
                }
            }
        }
        
        # Initialize
        controller._load_config()
        controller._initialize_zones()
        
        # Set up zone states
        controller.zones["living"].is_active = True
        controller.zones["living"].current_temp = 21.0
        controller.zones["living"].target_temp = 22.0
        
        controller.zones["baby_bed"].is_active = True
        controller.zones["baby_bed"].current_temp = 19.0
        controller.zones["baby_bed"].target_temp = 20.0
        
        # Test damper calculation
        trigger_zones = ["living"]
        positions = controller._calculate_damper_positions(trigger_zones)
        
        # Verify results
        assert positions["living"] == 50  # Primary zone
        assert positions["baby_bed"] == 0  # Isolated zone
        
        print("✓ Damper calculation successful")
        return True
    except Exception as e:
        print(f"✗ Damper calculation failed: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
        return False

def test_hvac_mode_setting():
    """Test HVAC mode setting"""
    try:
        controller = SmartAirconController()
        
        # Mock the dependencies
        controller.log = Mock()
        controller.get_state = Mock(return_value="dry")  # Current mode
        controller.call_service = Mock()
        controller.run_every = Mock()
        controller._entity_exists = Mock(return_value=True)
        
        # Mock configuration
        controller.args = {
            "enabled": True,
            "main_climate": "climate.aircon"
        }
        
        # Initialize
        controller._load_config()
        
        # Test mode setting
        controller._set_hvac_mode(HVACMode.HEAT)
        
        # Verify service call
        controller.call_service.assert_called_with(
            "climate/set_hvac_mode",
            entity_id="climate.aircon",
            hvac_mode="heat"
        )
        
        print("✓ HVAC mode setting successful")
        return True
    except Exception as e:
        print(f"✗ HVAC mode setting failed: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
        return False

def test_interface_services():
    """Test interface service registration"""
    try:
        interface = SmartAirconControllerInterface()
        
        # Mock the dependencies
        interface.log = Mock()
        interface.get_app = Mock()
        interface.register_service = Mock()
        interface.set_state = Mock()
        interface.run_every = Mock()
        
        # Mock controller
        mock_controller = Mock()
        interface.controller = mock_controller
        
        # Test service toggle
        interface._service_toggle("ns", "domain", "service", {"enabled": True})
        
        # Verify controller was called
        mock_controller.toggle_controller.assert_called_once_with(True)
        
        print("✓ Interface services successful")
        return True
    except Exception as e:
        print(f"✗ Interface services failed: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
        return False

def run_tests():
    """Run all tests"""
    print("Running Smart Aircon Controller Tests...")
    print("=" * 50)
    
    tests = [
        test_basic_imports,
        test_controller_creation,
        test_interface_creation,
        test_controller_config_loading,
        test_zone_initialization,
        test_damper_calculation,
        test_hvac_mode_setting,
        test_interface_services
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed with exception: {e}")
            failed += 1
    
    print("=" * 50)
    print(f"Tests completed: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed!")
        return True
    else:
        print(f"❌ {failed} tests failed")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1) 