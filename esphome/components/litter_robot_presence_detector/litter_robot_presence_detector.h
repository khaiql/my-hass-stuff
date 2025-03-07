#pragma once

#ifdef USE_ESP32

#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

#include "esphome/core/component.h"
#include "esphome/core/application.h"
#include "esphome/components/esp32_camera/esp32_camera.h"
#include "esphome/components/text_sensor/text_sensor.h"

#include <tensorflow/lite/core/c/common.h>
#include <tensorflow/lite/micro/micro_interpreter.h>
#include <tensorflow/lite/micro/micro_mutable_op_resolver.h>
#include <string>

// #define USE_EMA 1

namespace esphome {
namespace litter_robot_presence_detector {

constexpr size_t PREDICTION_HISTORY_SIZE = 7;
static std::string CLASSES[] = {"empty", "nachi", "ngao"};

class LitterRobotPresenceDetector : public Component, public text_sensor::TextSensor {
 public:
  // constructor
  LitterRobotPresenceDetector() : Component() {}

  void on_shutdown() override;
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override;

 protected:
  std::shared_ptr<esphome::esp32_camera::CameraImage> wait_for_image_();
  SemaphoreHandle_t semaphore_;
  std::shared_ptr<esphome::esp32_camera::CameraImage> image_;
  uint8_t *tensor_arena_{nullptr};
  uint8_t *input_buffer{nullptr};
  const tflite::Model *model{nullptr};
  tflite::MicroInterpreter *interpreter{nullptr};

#ifndef USE_EMA
  uint8_t prediction_history[PREDICTION_HISTORY_SIZE] = {0};
  int last_index{0};
#else
  double current_predictions[3] = {0.0, 0.0, 0.0};
  double ema_alpha{0.2};
#endif

  bool setup_model();
  bool register_preprocessor_ops(tflite::MicroMutableOpResolver<9> &micro_op_resolver);
  bool start_infer(std::shared_ptr<esphome::esp32_camera::CameraImage> image);
  int get_prediction_result();
  int decide_state(int max_index);
  bool decode_jpg(camera_fb_t *rb);
};
}  // namespace litter_robot_presence_detector
}  // namespace esphome

#endif
