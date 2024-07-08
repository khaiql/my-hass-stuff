import appdaemon.plugins.hass.hassapi as hass
from ac_zone import Zone

class ACSwitchStateManager(hass.Hass):
  async def initialize(self):
    ad_api = self.get_ad_api()
    self.bedroom_zone = Zone(ad_api, "bedroom", config=self.args["bedroom"])
    self.kitchen_zone = Zone(ad_api, "kitchen", config=self.args["kitchen"])
    self.study_zone = Zone(ad_api, "study", config=self.args["study"])

    self.zones = [self.bedroom_zone, self.kitchen_zone, self.study_zone]

    for zone in self.zones:
      zone.fingerbot_switch.listen_state(self.switch_state_callback)

    for state in [self.bedroom_zone, self.kitchen_zone, self.study_zone]:
      state.listen_state(self.automation_zone_callback)


  async def switch_state_callback(self, entity, attribute, old, new, **kwargs):
    self.log(f"switch_state_callback {entity=} {old=} {new=}")

    if await self.kitchen_zone.is_switch_state('off') and await self.study_zone.is_switch_state('off') and not await self.bedroom_zone.is_switch_state('on'):
      await self.bedroom_zone.revert_switch_state_without_clicking()

  async def automation_zone_callback(self, zone_state_entity, attribute, old, new, **kwargs):
    self.log(f"zone_callback {zone_state_entity=} {old=} {new=}")
    zone = next((zone for zone in self.zones if zone.zone_state.entity_id == zone_state_entity), None)
    if not zone:
      self.log(f"zone {zone_state_entity} not found ")
      return

    if new == 'off' and not zone.is_switch_state('off'):
      zone.toggle_switch_and_wait_state('off')
