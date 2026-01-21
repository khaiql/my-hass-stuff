#pragma once

#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

#include "esphome/components/esp32_camera/esp32_camera.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/core/application.h"
#include "esphome/core/component.h"
#include "litter_robot_detect.hpp"

#include <atomic>
#include <mutex>
#include <string>

// #define USE_EMA 1

namespace esphome {
namespace litter_robot_presence_detector {
constexpr size_t PREDICTION_HISTORY_SIZE = 7;

class LitterRobotPresenceDetector : public Component, public text_sensor::TextSensor, public camera::CameraListener {
 public:
  // constructor
  LitterRobotPresenceDetector() : Component() {}

  void on_shutdown() override;
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override;

  SemaphoreHandle_t semaphore;

 protected:
  EventGroupHandle_t inference_event_group;
  camera::Camera *camera_instance{nullptr};
  ::litter_robot_detect::CatDetect *cat_detector{nullptr};
  litter_robot_detect::prediction_result_t prediction_result;

  std::mutex image_mutex_;
  std::shared_ptr<esphome::camera::CameraImage> image_;

  TaskHandle_t inference_task_handle_{nullptr};
  static void inference_task_trampoline(void *params);
  void inference_task();
  void on_camera_image(const std::shared_ptr<esphome::camera::CameraImage> &image) override;
#ifndef USE_EMA
  uint8_t prediction_history[PREDICTION_HISTORY_SIZE] = {0};
  int last_index{0};
#else
  double current_predictions[3] = {0.0, 0.0, 0.0};
  double ema_alpha{0.2};
#endif
};
}  // namespace litter_robot_presence_detector
}  // namespace esphome
