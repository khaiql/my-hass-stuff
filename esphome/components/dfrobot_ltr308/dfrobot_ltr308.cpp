#include "dfrobot_ltr308.h"
#include "esphome/core/log.h"
#include "esphome/core/hal.h"
#include <cstdint>

namespace esphome {
namespace dfrobot_ltr308 {

static const char *const TAG = "dfrobot_ltr308";

static const uint8_t LTR308_REG_CONTR = 0x00;
static const uint8_t LTR308_REG_MEAS_RATE = 0x04;
static const uint8_t LTR308_REG_ALS_GAIN = 0x05;
static const uint8_t LTR308_REG_PART_ID = 0x06;
static const uint8_t LTR308_REG_STATUS = 0x07;
static const uint8_t LTR308_REG_DATA_0 = 0x0D;
static const uint8_t LTR308_REG_INTERRUPT = 0x19;
static const uint8_t LTR308_REG_INTR_PERS = 0x1A;
static const uint8_t LTR308_REG_THRES_UP_0 = 0x21;
static const uint8_t LTR308_REG_THRES_LOW_0 = 0x24;

void DFRobotLTR308Component::setup() {
  ESP_LOGCONFIG(TAG, "Setting up DFRobot LTR308...");

  uint8_t part_id;
  if (!this->read_byte(LTR308_REG_PART_ID, &part_id)) {
    ESP_LOGE(TAG, "Failed to read part ID");
    this->mark_failed();
    return;
  }

  if (part_id != 0xB1) {
    ESP_LOGE(TAG, "Invalid part ID: 0x%02X", part_id);
    this->mark_failed();
    return;
  }

  // Power up
  this->write_byte(LTR308_REG_CONTR, 0x02);
  delay(10);

  // Set gain
  this->write_byte(LTR308_REG_ALS_GAIN, (uint8_t) this->gain_);

  // Set measurement rate and resolution
  uint8_t meas_rate = (this->resolution_ << 4) | this->rate_;
  this->write_byte(LTR308_REG_MEAS_RATE, meas_rate);

  if (this->interrupt_pin_ != nullptr) {
    this->interrupt_pin_->setup();
    this->interrupt_pin_->attach_interrupt(DFRobotLTR308Component::isr, this, gpio::INTERRUPT_FALLING_EDGE);

    // thresholds are lux, convert to raw counts (approximate)
    uint32_t high_raw = (uint32_t) (this->threshold_high_ / 0.6f);
    uint32_t low_raw = (uint32_t) (this->threshold_low_ / 0.6f);

    uint8_t data[6];
    data[0] = high_raw & 0xFF;
    data[1] = (high_raw >> 8) & 0xFF;
    data[2] = (high_raw >> 16) & 0x0F;
    data[3] = low_raw & 0xFF;
    data[4] = (low_raw >> 8) & 0xFF;
    data[5] = (low_raw >> 16) & 0x0F;
    this->write_bytes(LTR308_REG_THRES_UP_0, data, 6);

    this->write_byte(LTR308_REG_INTR_PERS, 0x00);  // 1 trigger
    this->write_byte(LTR308_REG_INTERRUPT, 0x14);  // Enable interrupt
  }

  if (this->ir_led_pin_ != nullptr) {
    this->ir_led_pin_->setup();
    this->ir_led_pin_->digital_write(false);
  }
}

void DFRobotLTR308Component::update() {
  if (this->is_failed()) {
    return;
  }

  if (this->interrupt_triggered_) {
    this->handle_interrupt_();
    this->interrupt_triggered_ = false;
  }

  float lux = this->get_lux_();
  ESP_LOGV(TAG, "Lux: %.2f", lux);
  this->publish_state(lux);
}

void DFRobotLTR308Component::dump_config() {
  LOG_SENSOR("", "DFRobot LTR308", this);
  LOG_I2C_DEVICE(this);
  ESP_LOGCONFIG(TAG, "  Gain Enum: %d", (int) this->gain_);
  ESP_LOGCONFIG(TAG, "  Resolution Enum: %d", (int) this->resolution_);
  ESP_LOGCONFIG(TAG, "  Rate Enum: %d", (int) this->rate_);
  ESP_LOGCONFIG(TAG, "  Threshold High: %.2f Lux", this->threshold_high_);
  ESP_LOGCONFIG(TAG, "  Threshold Low: %.2f Lux", this->threshold_low_);
  LOG_PIN("  Interrupt Pin: ", this->interrupt_pin_);
  LOG_PIN("  IR LED Pin: ", this->ir_led_pin_);
  LOG_BINARY_SENSOR("  ", "IR LED Status Sensor", this->ir_led_status_sensor_);
  if (this->is_failed()) {
    ESP_LOGCONFIG(TAG, "  Initialization failed!");
  }
}

uint32_t DFRobotLTR308Component::read_data_() {
  uint8_t data[3];
  if (!this->read_bytes(LTR308_REG_DATA_0, data, 3)) {
    return 0;
  }
  return ((uint32_t) (data[2] & 0x0F) << 16) | ((uint32_t) data[1] << 8) | (uint32_t) data[0];
}

float DFRobotLTR308Component::get_lux_(uint32_t raw) {
  float lux = raw * 0.6f;

  // Gain factor
  switch (this->gain_) {
    case GAIN_1X:
      break;
    case GAIN_3X:
      lux /= 3.0f;
      break;
    case GAIN_6X:
      lux /= 6.0f;
      break;
    case GAIN_9X:
      lux /= 9.0f;
      break;
    case GAIN_18X:
      lux /= 18.0f;
      break;
  }

  // Resolution factor
  switch (this->resolution_) {
    case RES_400MS_20B:
      lux /= 4.0f;
      break;
    case RES_200MS_19B:
      lux /= 2.0f;
      break;
    case RES_100MS_18B:
      break;
    case RES_50MS_17B:
      lux *= 2.0f;
      break;
    case RES_25MS_16B:
      lux *= 4.0f;
      break;
  }
  return lux;
}

void IRAM_ATTR DFRobotLTR308Component::isr(DFRobotLTR308Component *arg) { arg->interrupt_triggered_ = true; }

void DFRobotLTR308Component::handle_interrupt_() {
  uint8_t status;
  if (this->read_byte(LTR308_REG_STATUS, &status)) {
    if (status & 0x10) {  // intrStatus
      float lux = this->get_lux_();
      ESP_LOGD(TAG, "Interrupt! Lux: %.2f", lux);
      if (lux < this->threshold_low_) {
        if (this->ir_led_pin_ != nullptr) {
          this->ir_led_pin_->digital_write(true);
        }
        if (this->ir_led_status_sensor_ != nullptr) {
          this->ir_led_status_sensor_->publish_state(true);
        }
      } else if (lux > this->threshold_low_ + 5.0f) {
        if (this->ir_led_pin_ != nullptr) {
          this->ir_led_pin_->digital_write(false);
        }
        if (this->ir_led_status_sensor_ != nullptr) {
          this->ir_led_status_sensor_->publish_state(false);
        }
      }
    }
  }
}

}  // namespace dfrobot_ltr308
}  // namespace esphome
