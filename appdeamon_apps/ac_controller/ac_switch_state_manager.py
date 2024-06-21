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
      switch.listen_state(self.reconcile_switch_states)

    for state in [self.bedroom_state, self.kitchen_state, self.study_state]:
      state.listen_state(self.toggle_switch_based_on_zone_state)


  def reconcile_switch_states(self, *args, **kwargs):
    if self.kitchen_switch.is_state('off') and self.study_switch.is_state('off'):
      self.bedroom_switch.set_state(state='on')

  def toggle_switch_based_on_zone_state(self, zone_state, attribute, old, new, **kwargs):
    switch = self.switches_dict[zone_state]
    if not switch.is_state(new):
      switch.toggle()
