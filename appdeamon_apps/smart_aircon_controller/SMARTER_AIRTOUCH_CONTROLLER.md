## Problem

The default controller from Airtouch 5 is very energy inefficient, sometimes buggy, espectially at night. The main problem that I see is that, if there are 2 or 3 zones turning on at the same time, and have some differences in set point temperature, for example:

Masterbed:
- Set point: 19
Baby bed
- Set point: 20
Guest bed:
- Set point 18

Babybed has the highest set point, so for example when Babybed room temp decreases to 19.5, the compression will start again to heat up. Other rooms' temperature are still within the range, let's say 19.0, and 17.9 respectively or master and guest bed. It will mostly just open the damper to the baby bed, and won't be opening the other two dampers to utlize the energy and heat up those rooms as well.

Another bug that I observed is that even with only one room turned on, babybed for example, setting temp to 20, at some point later of the night, it'll just keep the compressor running constantly and maintain the room temperature around the set point with very little standard deviation. For example normally it will heat up to 20.5, then shut off compressor, or slowly opening the damper and turn on compressor when it approaching 19.5. There is a time gap to reduce from 20.5 to 19.5 and that is energy efficient. But when the bug happens, it runs entire time, and temperature will be around 20.2 to 19.8.

## Solution

Let's say there is an extra parameter call temp_std, which is for standard deviation, (help me with a better name if possible) that allows the room temp to be within that range, outside that range, it'll either turn off or turn on the compressor. For example, temp_std = 0.5, means it'll heat up to 20.5, and start heating again when temp reduces to 19.5. Of course we want a smooth opening/closing of the damper, not just an abruptedly close or open the damper, for example slowly closing the damper percentage to 10% or 5% when the room temp reach 20.5, or slowly open the damper when room temp approaching 19.5.

We detect that when the temperature of a room is decreasing to a point that it needs to be heat up again, we also slowly opening the damper of the other currently active zones as well, even though other rooms' temperature haven't decreased too low, to leverage the heat, instead of individual heat each zone.

A concrete example with 3 active zones like the above
- When baby bed room temp reaches 19.5, opens the damper to 50%. Masterbed's temperature is still at 19.2 (still within the room temp +- temp_std). Guest bed at this point is 18.6, higher than 18+-0.5. So the controller will opens the master bed's damper to 40% or 50% as well, but keep the guest bed damper closed, or only opens at 10%, the higher the temp, the smaller the damper open. This is to ensure we don't overheat the room from the set point and cause uncomfortable. The main idea is to maintain room temperature within the std deviation.
- The HVAC will be switched from DRY to HEAT mode, and let the A/C heat up all the rooms at the same time.
- When the triggered zone (baby bed) in this case, reaches 20.5, the normal Airtouch controller should have slowly closed the baby bed damper by this time, maybe it'll be 5% open or closed, then the automation intervene and change HVAC mode back to DRY. However, we only change it to DRY when all the active zones are now within the desired temperature, set point <= room temp <= set point + standard deviation.

There should be a similar algorithm but for cooling mode though.

**IMPORTANT**: 
- When the A/C is in HEAT or COOL mode, the control is in Airtouch's hand, and the damper opening is managed by Airtouch. The automation only intervene and set to DRY or FAN mode when the temperature when needed to save energy. 
- The IDLE mode when heating is DRY, and when cooling is FAN. 


### When to switch from HEAT to DRY

graph TD
  A[Start] --> B{enabled?}
  B -->|Yes| C{smart hvac mode == heating?}
  B -->|No| E[End]
  C --> |yes| D{all active zones > desired temperature}
  D --> |yes| F{all active zones' damper <= 10%}
  F --> |yes| G[Switch to DRY]
  G --> P[Set all zones' damper to 5%]
  D --> |no| L
  F --> |no| L[Keep as HEAT]
  L --> E
  P --> E

### When to switch from DRY to HEAT

graph TD
  A[Start] --> B{enabled?}
  B -->|Yes| C{smart hvac mode == heating?}
  B -->|No| E[End]
  C --> |yes| D{at least one active zone's temperature < set_point - tolerence}
  D --> |yes| F[Switch to HEAT]
  F --> G[Open damper in other active zones, depending on the diff between current tempt to set point]
  G --> E
  D --> H[keep in DRY]
  H --> E

### When to switch from COOL to FAN

graph TD
  A[Start] --> B{enabled?}
  B -->|Yes| C{smart hvac mode == cooling?}
  B -->|No| E[End]
  C --> |yes| D{all active zones < desired temperature}
  D --> |yes| F{all active zones' damper <= 10%}
  F --> |yes| G[Switch to FAN]
  G --> P[Set all zones' damper to 5%]
  D --> |no| L
  F --> |no| L[Keep as COOL]
  L --> E
  P --> E

### When to switch from FAN to COOL

graph TD
  A[Start] --> B{enabled?}
  B -->|Yes| C{smart hvac mode == cooling?}
  B -->|No| E[End]
  C --> |yes| D{at least one active zone's temperature > set_point + tolerance}
  D --> |yes| F[Switch to COOL]
  F --> G[Open damper in other active zones, depending on the diff between current temp to set point]
  G --> E
  D --> H[keep in FAN]
  H --> E
  
## Resources 

MUST READ: 
- https://appdaemon.readthedocs.io/en/latest/_sources/AD_API_REFERENCE.rst.txt
- https://appdaemon.readthedocs.io/en/latest/_sources/APPGUIDE.rst.txt
