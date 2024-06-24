import appdaemon.plugins.hass.hassapi as hass

class ACSwitchStateManager(hass.Hass):
  def initialize(self):

    self.log(f"args {self.args}")
    self.bedroom_switch = self.get_entity(self.args['bedroom']['switch_entity'])
    self.bedroom_state = self.get_entity(self.args['bedroom']['state_entity'])

    self.kitchen_switch = self.get_entity(self.args['kitchen']['switch_entity'])
    self.kitchen_state = self.get_entity(self.args['kitchen']['state_entity'])

    self.study_switch = self.get_entity(self.args['study']['switch_entity'])
    self.study_state = self.get_entity(self.args['study']['state_entity'])

    self.switches_dict = {
      self.bedroom_state.entity_id: self.bedroom_switch,
      self.kitchen_state.entity_id: self.kitchen_switch,
      self.study_state.entity_id: self.study_switch,
    }

    self.log(f"dictionary {self.switches_dict}")

    for switch in self.switches_dict.values():
      switch.listen_state(self.switch_state_callback)

    for state in [self.bedroom_state, self.kitchen_state, self.study_state]:
      state.listen_state(self.automation_zone_callback)


  def switch_state_callback(self, entity, attribute, old, new, **kwargs):
    if old == new:
      self.log(f"getting odd case for {entity} where old == new == {new}")

    if self.kitchen_switch.is_state('off') and self.study_switch.is_state('off') and not self.bedroom_switch.is_state('on'):
      self.bedroom_switch.set_state(state='on')

  def automation_zone_callback(self, zone_state, attribute, old, new, **kwargs):
    switch = self.switches_dict[zone_state]
    if new == 'off' and not switch.is_state('off'):
      switch.toggle()
