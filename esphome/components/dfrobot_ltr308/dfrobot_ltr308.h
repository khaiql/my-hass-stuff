#pragma once

#include "esphome/core/component.h"
#include "esphome/core/hal.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/i2c/i2c.h"
#include <cstdint>

namespace esphome {
namespace dfrobot_ltr308 {

enum DFRobotLTR308Gain {
  GAIN_1X = 0x00,
  GAIN_3X = 0x01,
  GAIN_6X = 0x02,
  GAIN_9X = 0x03,
  GAIN_18X = 0x04,
};

enum DFRobotLTR308Resolution {
  RES_400MS_20B = 0x00,
  RES_200MS_19B = 0x01,
  RES_100MS_18B = 0x02,
  RES_50MS_17B = 0x03,
  RES_25MS_16B = 0x04,
};

enum DFRobotLTR308Rate {
  RATE_25MS = 0x00,
  RATE_50MS = 0x01,
  RATE_100MS = 0x02,
  RATE_500MS = 0x03,
  RATE_1000MS = 0x05,
  RATE_2000MS = 0x06,
};

class DFRobotLTR308Component : public PollingComponent, public sensor::Sensor, public i2c::I2CDevice {
 public:
  void setup() override;
  void update() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  void set_gain(DFRobotLTR308Gain gain) { gain_ = gain; }
  void set_resolution(DFRobotLTR308Resolution res) { resolution_ = res; }
  void set_rate(DFRobotLTR308Rate rate) { rate_ = rate; }
  void set_threshold_high(float lux) { threshold_high_ = lux; }
  void set_threshold_low(float lux) { threshold_low_ = lux; }
  void set_interrupt_pin(InternalGPIOPin *pin) { interrupt_pin_ = pin; }
  void set_ir_led_pin(InternalGPIOPin *pin) { ir_led_pin_ = pin; }
  void set_ir_led_status_sensor(binary_sensor::BinarySensor *sensor) { ir_led_status_sensor_ = sensor; }

 protected:
  static void isr(DFRobotLTR308Component *arg);
  void handle_interrupt_();

  float get_lux_() { return get_lux_(read_data_()); }
  uint32_t read_data_();
  float get_lux_(uint32_t raw);

  DFRobotLTR308Gain gain_{GAIN_3X};
  DFRobotLTR308Resolution resolution_{RES_100MS_18B};
  DFRobotLTR308Rate rate_{RATE_100MS};
  float threshold_high_{500.0f};
  float threshold_low_{10.0f};
  InternalGPIOPin *interrupt_pin_{nullptr};
  InternalGPIOPin *ir_led_pin_{nullptr};
  binary_sensor::BinarySensor *ir_led_status_sensor_{nullptr};

  volatile bool interrupt_triggered_{false};
};

}  // namespace dfrobot_ltr308
}  // namespace esphome
