# Smart Aircon Controller for Airtouch 5

An intelligent controller for Airtouch 5 systems that improves energy efficiency by coordinating heating/cooling across multiple zones.

## Features

- **Energy Efficient**: Leverages heat across multiple zones instead of heating each zone individually
- **Smart Coordination**: When one zone needs heating, other zones can benefit from shared heating
- **Configurable**: Customizable temperature tolerance and damper settings
- **Safe**: Supports zone isolation (e.g., baby rooms) that won't participate in shared heating
- **Monitoring**: Provides sensors and services for Home Assistant integration

## How It Works

1. **Zone Monitoring**: Continuously monitors all active zones' temperatures
2. **Trigger Detection**: Detects when a zone needs heating (temp < target - tolerance)
3. **Smart Damper Control**: Opens dampers for:
   - Primary zone: 50% (configurable)
   - Secondary zones that could benefit: 40% (configurable)
   - Zones close to target: 10% (configurable)
4. **HVAC Coordination**: Switches main AC to HEAT mode during smart heating
5. **Completion**: Returns to DRY mode when all zones are satisfied

## Installation

1. **Copy files** to your AppDaemon apps directory:
   ```
   /config/appdaemon/apps/smart_aircon_controller/
   ├── smart_aircon_controller.py
   ├── controller_interface.py
   ├── apps.yaml
   └── README.md
   ```

2. **Update your main apps.yaml** to include the smart_aircon_controller configuration:
   ```yaml
   # Add this to your main /config/appdaemon/apps/apps.yaml
   smart_aircon_controller:
     module: smart_aircon_controller.smart_aircon_controller
     class: SmartAirconController
     # ... rest of configuration from apps.yaml
   ```

3. **Restart AppDaemon** to load the new app

## Configuration

### Zone Setup

Update the `zones` section in `apps.yaml` to match your Home Assistant entities:

```yaml
zones:
  living:
    climate_entity: climate.living          # Your zone climate entity
    damper_entity: cover.living_damper      # Your zone damper entity  
    temp_sensor: sensor.living_temperature  # Your zone temperature sensor
    isolation: false                        # Allow shared heating
  baby_bed:
    climate_entity: climate.baby_bed
    damper_entity: cover.baby_bed_damper
    temp_sensor: sensor.baby_bed_temperature
    isolation: true                         # Isolated - no shared heating
```

### Key Parameters

- **temp_tolerance**: Temperature range around setpoint (default: 0.5°C)
- **check_interval**: How often to check zones (default: 30 seconds)
- **primary_damper_percent**: Damper opening for triggering zone (default: 50%)
- **secondary_damper_percent**: Damper opening for secondary zones (default: 40%)
- **overflow_damper_percent**: Minimal damper opening for zones near target (default: 10%)

## Home Assistant Integration

### Sensors

The controller creates these sensors in Home Assistant:

- `sensor.smart_aircon_enabled` - Controller on/off status
- `sensor.smart_aircon_algorithm_active` - Algorithm currently running
- `sensor.smart_aircon_hvac_mode` - Current HVAC mode
- `sensor.smart_aircon_active_zones` - Number of active zones with details

### Services

Available services for automation:

```yaml
# Toggle the controller
service: appdaemon.smart_aircon_toggle
data:
  enabled: true

# Get status
service: appdaemon.smart_aircon_get_status

# Set temperature tolerance
service: appdaemon.smart_aircon_set_temp_tolerance
data:
  tolerance: 0.7
```

## Example Automations

### Enable/Disable Based on Time

```yaml
automation:
  - alias: "Enable Smart Aircon During Night"
    trigger:
      platform: time
      at: "22:00:00"
    action:
      service: appdaemon.smart_aircon_toggle
      data:
        enabled: true

  - alias: "Disable Smart Aircon During Day"
    trigger:
      platform: time
      at: "08:00:00"
    action:
      service: appdaemon.smart_aircon_toggle
      data:
        enabled: false
```

### Dashboard Card

```yaml
type: entities
title: Smart Aircon Controller
entities:
  - entity: sensor.smart_aircon_enabled
    name: "Controller Status"
  - entity: sensor.smart_aircon_algorithm_active
    name: "Algorithm Running"
  - entity: sensor.smart_aircon_hvac_mode
    name: "HVAC Mode"
  - entity: sensor.smart_aircon_active_zones
    name: "Active Zones"
```

## Monitoring and Troubleshooting

### AppDaemon Logs

Check AppDaemon logs for controller activity:
```
tail -f /config/appdaemon/logs/appdaemon.log | grep "Smart Aircon"
```

### Common Issues

1. **Zone not found warnings**: Check entity IDs in configuration match your Home Assistant setup
2. **Damper not responding**: Verify damper entities are working manually
3. **HVAC mode not changing**: Check main climate entity permissions

### Debug Mode

Enable debug logging in AppDaemon configuration:
```yaml
# /config/appdaemon/apps/apps.yaml
logs:
  smart_aircon_controller:
    level: DEBUG
```

## Algorithm Logic

### Heating Mode

```
For each active zone:
  If zone_temp < (target_temp - tolerance):
    Primary zone: Open damper to 50%
    Other zones:
      If temp_diff > 0: Open damper to 40% (can benefit)
      If temp_diff > -tolerance: Open damper to 10% (minimal)
      If isolated: Keep damper closed
    Switch HVAC to HEAT
    
  When all zones satisfied:
    Switch HVAC to DRY
    Let Airtouch resume normal control
```

### Safety Features

- **Zone isolation**: Baby rooms and other sensitive areas won't participate in shared heating
- **Entity validation**: Checks all entities exist before starting
- **Error handling**: Graceful handling of sensor failures and communication errors
- **Manual override**: Detects manual changes and adapts accordingly

## Future Enhancements

- [ ] Cooling mode implementation
- [ ] Time-based temperature tolerance adjustment
- [ ] Machine learning for optimal damper positions
- [ ] Integration with weather forecasts
- [ ] Energy usage monitoring and reporting

## Support

For issues or questions:
1. Check AppDaemon logs first
2. Verify entity configurations
3. Test manual damper and climate control
4. Check Home Assistant entity states

## License

This project is provided as-is for personal use. Modify and adapt as needed for your specific setup. 