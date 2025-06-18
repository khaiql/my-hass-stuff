#!/usr/bin/env python3
"""Debug script to check import issues"""

import sys
import types
sys.path.insert(0, '.')
from unittest.mock import Mock, MagicMock

print("Setting up mocks...")

class MockHass:
    def __init__(self):
        print("MockHass init called")
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

print("Mocks set up, now importing...")

# Now try to import
from smart_aircon_controller import SmartAirconController
print('Type of SmartAirconController:', type(SmartAirconController))
print('Is it a Mock?', isinstance(SmartAirconController, Mock))
print('Is it a MagicMock?', isinstance(SmartAirconController, MagicMock))

# Check the parent class
print('SmartAirconController bases:', SmartAirconController.__bases__)
print('SmartAirconController MRO:', SmartAirconController.__mro__)

# Try to create an instance
print("Creating instance...")
try:
    controller = SmartAirconController()
    print('Type of controller instance:', type(controller))
    print('Is controller a Mock?', isinstance(controller, Mock))
    print('Is controller a MagicMock?', isinstance(controller, MagicMock))
    print("Instance created successfully!")
    
    # Try to set some args and call a method
    controller.args = {"enabled": True, "temp_tolerance": 0.5}
    controller._load_config()
    print("Config loading worked!")
    print(f"Controller enabled: {controller.config.enabled}")
    print(f"Controller tolerance: {controller.config.temp_tolerance}")
    
except Exception as e:
    print(f"Error creating instance: {e}")
    import traceback
    traceback.print_exc() 