#include "litter_robot_presence_detector.h"
#include "esphome/core/log.h"

#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "model_data.h"
#include <time.h>
#include <string>

#include "jpeg_decoder.h"

namespace esphome
{
  namespace litter_robot_presence_detector
  {

    static const char *const TAG = "litter_robot_presence_detector";
    static const uint32_t MODEL_ARENA_SIZE = 200 * 1024;
    // static const uint32_t INPUT_BUFFER_SIZE = 144 * 176 * 3 * sizeof(uint8_t);

    float LitterRobotPresenceDetector::get_setup_priority() const { return setup_priority::AFTER_CONNECTION; }

    void LitterRobotPresenceDetector::on_shutdown()
    {
      this->image_ = nullptr;
      if (this->inference_task_handle_ != nullptr)
      {
        vTaskDelete(this->inference_task_handle_);
        this->inference_task_handle_ = nullptr;
      }
      vSemaphoreDelete(this->semaphore_);
      this->semaphore_ = nullptr;
    }

    void LitterRobotPresenceDetector::inference_task_trampoline(void *params)
    {
      LitterRobotPresenceDetector *detector = (LitterRobotPresenceDetector *)params;
      detector->inference_task();
    }

    void LitterRobotPresenceDetector::inference_task()
    {
      while (true)
      {
        if (this->is_failed())
        {
          vTaskDelete(NULL);
        }

        // Delay to prevent 100% CPU usage and allow other tasks to run
        // 1 second delay
        vTaskDelay(pdMS_TO_TICKS(1000));

        if (!this->is_ready())
        {
          ESP_LOGW(TAG, "not ready yet, skip!");
          continue;
        }

        esp32_camera::global_esp32_camera->request_image(esphome::esp32_camera::API_REQUESTER);
        auto image = this->wait_for_image_();

        if (!image)
        {
          ESP_LOGW(TAG, "SNAPSHOT: failed to acquire frame");
          continue;
        }
        this->image_ = nullptr;

        if (!this->start_infer(image))
        {
          ESP_LOGE(TAG, "infer failed");
        }
        else
        {
          int prediction_index = this->get_prediction_result();
          int index_to_update = this->decide_state(prediction_index);
          this->pending_state_ = CLASSES[index_to_update];
          this->result_ready_ = true;
          ESP_LOGI(TAG, "predicted class %s. Final state to update: %s", CLASSES[prediction_index].c_str(),
                   this->pending_state_.c_str());
        }
      }
    }

    bool LitterRobotPresenceDetector::register_preprocessor_ops(tflite::MicroMutableOpResolver<9> &micro_op_resolver)
    {
      if (micro_op_resolver.AddConv2D() != kTfLiteOk)
      {
        ESP_LOGE(TAG, "failed to register ops AddConv2D");
        return false;
      }

      if (micro_op_resolver.AddQuantize() != kTfLiteOk)
      {
        ESP_LOGE(TAG, "failed to register ops AddQuantize");
        return false;
      }

      if (micro_op_resolver.AddRelu() != kTfLiteOk)
      {
        ESP_LOGE(TAG, "failed to register ops AddRelu");
        return false;
      }

      if (micro_op_resolver.AddDepthwiseConv2D() != kTfLiteOk)
      {
        ESP_LOGE(TAG, "failed to register ops AddDepthwiseConv2D");
        return false;
      }

      if (micro_op_resolver.AddFullyConnected() != kTfLiteOk)
      {
        ESP_LOGE(TAG, "failed to register ops AddFullyConnected");
        return false;
      }

      if (micro_op_resolver.AddSoftmax() != kTfLiteOk)
      {
        ESP_LOGE(TAG, "failed to register ops AddSoftmax");
        return false;
      }

      if (micro_op_resolver.AddMean() != kTfLiteOk)
      {
        ESP_LOGE(TAG, "failed to register ops AddMean");
        return false;
      }

      return true;
    }

    bool LitterRobotPresenceDetector::decode_jpg(camera_fb_t *rb)
    {
      TfLiteTensor *input = this->interpreter->input(0);

      // Safety check: ensure decoded image fits in tensor input
      // Assuming RGB888 output (3 bytes per pixel)
      size_t required_size = rb->width * rb->height * 3 * sizeof(uint8_t);
      if (required_size > input->bytes)
      {
        ESP_LOGE(TAG, "Decoded image size (%d) exceeds tensor input size (%d). Check camera resolution.", required_size, input->bytes);
        return false;
      }

      esp_jpeg_image_cfg_t jpeg_cfg = {.indata = (uint8_t *)rb->buf,
                                       .indata_size = rb->len,
                                       .outbuf = input->data.uint8, // Decode directly to tensor input
                                       .outbuf_size = static_cast<int>(input->bytes),
                                       .out_format = JPEG_IMAGE_FORMAT_RGB888,
                                       .out_scale = JPEG_IMAGE_SCALE_0,
                                       .flags = {
                                           .swap_color_bytes = 0,
                                       }};
      esp_jpeg_image_output_t outimg;

      esp_err_t res = esp_jpeg_decode(&jpeg_cfg, &outimg);
      if (res != ESP_OK)
      {
        ESP_LOGE(TAG, "JPEG decode failed");
        return false;
      }

      // Fix for signed int8 models: convert [0,255] to [-128,127]
      // TFLite quantization often expects int8 inputs (-128 to 127) internally.
      // If inference_input_type was not strictly enforced or if the model
      // lacks a Cast/Quantize op at the entry, the input tensor might be int8.
      // Passing raw uint8 [0,255] results in wrapping (128 becomes -128), ruining predictions.
      if (input->type == kTfLiteInt8)
      {
        uint8_t *data = input->data.uint8;
        for (size_t i = 0; i < input->bytes; i++)
        {
          // xor 0x80 is equivalent to subtracting 128 for byte-sized values
          // 0 (0x00) ^ 0x80 = 128 (0x80) -> interpreted as -128
          // 255 (0xFF) ^ 0x80 = 127 (0x7F) -> interpreted as 127
          data[i] ^= 0x80;
        }
      }

      ESP_LOGD(TAG, "out img width=%d height=%d", outimg.width, outimg.height);
      return true;
    }

    bool LitterRobotPresenceDetector::setup_model()
    {
      ExternalRAMAllocator<uint8_t> arena_allocator(ExternalRAMAllocator<uint8_t>::ALLOW_FAILURE);
      this->tensor_arena_ = arena_allocator.allocate(MODEL_ARENA_SIZE);
      if (this->tensor_arena_ == nullptr)
      {
        ESP_LOGE(TAG, "Could not allocate the streaming model's tensor arena.");
        return false;
      }

      // Removed input_buffer allocation as we now write directly to tensor input

      this->model = ::tflite::GetModel(g_model_data);
      if (this->model->version() != TFLITE_SCHEMA_VERSION)
      {
        ESP_LOGE(TAG,
                 "Model provided is schema version %d not equal "
                 "to supported version %d.\n",
                 this->model->version(), TFLITE_SCHEMA_VERSION);
        return false;
      }

      static tflite::MicroMutableOpResolver<9> micro_op_resolver;
      if (!this->register_preprocessor_ops(micro_op_resolver))
      {
        ESP_LOGE(TAG, "Register ops failed");
        return false;
      }

      static tflite::MicroInterpreter static_interpreter(this->model, micro_op_resolver, this->tensor_arena_,
                                                         MODEL_ARENA_SIZE);
      this->interpreter = &static_interpreter;

      TfLiteStatus allocate_status = interpreter->AllocateTensors();
      if (allocate_status != kTfLiteOk)
      {
        ESP_LOGE(TAG, "AllocateTensors() failed");
        return false;
      }

      ESP_LOGD(TAG, "setup model successfully");

      return true;
    }

    void LitterRobotPresenceDetector::setup()
    {
      ESP_LOGD(TAG, "Begin setup");

      // SETUP CAMERA
      if (!esp32_camera::global_esp32_camera || esp32_camera::global_esp32_camera->is_failed())
      {
        ESP_LOGW(TAG, "setup litter robot presence detector failed");
        this->mark_failed();
        return;
      }

      if (!this->setup_model())
      {
        ESP_LOGE(TAG, "setup model failed");
        this->mark_failed();
        return;
      }

      this->semaphore_ = xSemaphoreCreateBinary();

      esp32_camera::global_esp32_camera->add_image_callback([this](std::shared_ptr<esp32_camera::CameraImage> image)
                                                            {
        ESP_LOGD(TAG, "received image");
        if (image->was_requested_by(esp32_camera::API_REQUESTER)) {
          {
            std::lock_guard<std::mutex> lock(this->image_lock_);
            this->image_ = std::move(image);
          }
          xSemaphoreGive(this->semaphore_);
        } });

      // Create inference task on Core 1 (App Core) with 8KB stack
      xTaskCreatePinnedToCore(inference_task_trampoline, "inference_task", 8192, this, 1, &this->inference_task_handle_, 1);

      ESP_LOGD(TAG, "setup litter robot presence detector successfully");
    }

    void LitterRobotPresenceDetector::loop()
    {
      if (this->result_ready_)
      {
        this->publish_state(this->pending_state_);
        this->result_ready_ = false;
      }
    }

    void LitterRobotPresenceDetector::dump_config()
    {
      if (this->is_failed())
      {
        ESP_LOGE(TAG, "  Setup Failed");
        return;
      }
      TfLiteTensor *input = this->interpreter->input(0);
      TfLiteTensor *output = this->interpreter->output(0);

      ESP_LOGCONFIG(TAG, "Input");
      ESP_LOGCONFIG(TAG, "  - dim_size: %d", input->dims->size);
      ESP_LOGCONFIG(TAG, "  - input_dims (%d,%d,%d,%d)", input->dims->data[0], input->dims->data[1], input->dims->data[2],
                    input->dims->data[3]);
      ESP_LOGCONFIG(TAG, "  - zero_point=%d scale=%f", input->params.zero_point, input->params.scale);
      ESP_LOGCONFIG(TAG, "  - input_type: %d", input->type);
      ESP_LOGCONFIG(TAG, "Output");
      ESP_LOGCONFIG(TAG, "  - dim_size: %d", output->dims->size);
      ESP_LOGCONFIG(TAG, "  - dims (%d,%d)", output->dims->data[0], output->dims->data[1]);
      ESP_LOGCONFIG(TAG, "  - zero_point=%d scale=%f", output->params.zero_point, output->params.scale);
      ESP_LOGCONFIG(TAG, "  - output_type: %d", output->type);
    }

    std::shared_ptr<esphome::esp32_camera::CameraImage> LitterRobotPresenceDetector::wait_for_image_()
    {
      std::shared_ptr<esphome::esp32_camera::CameraImage> image;

      // Wait for the "doorbell" (callback) to signal that data is ready
      // 200 ticks = 2 seconds (assuming 10ms ticks) or 200ms depending on config.
      // Safe upper bound since camera should be fast.
      if (xSemaphoreTake(this->semaphore_, 200) == pdTRUE)
      {
        std::lock_guard<std::mutex> lock(this->image_lock_);
        image.swap(this->image_);
      }

      return image;
    }
    bool LitterRobotPresenceDetector::start_infer(std::shared_ptr<esphome::esp32_camera::CameraImage> image)
    {
      camera_fb_t *rb = image->get_raw_buffer();
      ESP_LOGD(TAG, " Received image size width=%d height=%d", rb->width, rb->height);

      uint32_t prior_invoke = millis();
      if (!this->decode_jpg(rb))
      {
        ESP_LOGE(TAG, "cant decode to rgb");
        return false;
      }

      // No need to memcpy, decode_jpg wrote directly to input tensor

      TfLiteStatus invokeStatus = this->interpreter->Invoke();
      ESP_LOGD(TAG, " Inference Latency=%u ms", (millis() - prior_invoke));
      return invokeStatus == kTfLiteOk;
    }

    int LitterRobotPresenceDetector::get_prediction_result()
    {
      TfLiteTensor *output = this->interpreter->output(0);

      auto empty_score = output->data.uint8[0];
      auto nachi_score = output->data.uint8[1];
      auto ngao_score = output->data.uint8[2];
      ESP_LOGD(TAG, "empty_score=%d nachi_score=%d ngao_score=%d", empty_score, nachi_score, ngao_score);

      uint8_t scores[] = {empty_score, nachi_score, ngao_score};
      int max_index = 0;
      for (int i = 1; i < 3; ++i)
      {
        if (scores[i] > scores[max_index])
        {
          max_index = i;
        }
      }

      return max_index;
    }

    int LitterRobotPresenceDetector::decide_state(int max_index)
    {
#ifndef USE_EMA
      // Update prediction history for each class
      this->prediction_history[this->last_index] = max_index;
      this->last_index += 1;
      if (this->last_index == PREDICTION_HISTORY_SIZE)
      {
        this->last_index = 0;
      }

      // Calculate the average score for each class
      uint8_t class_counts[3] = {0};
      for (int i = 0; i < PREDICTION_HISTORY_SIZE; i++)
      {
        class_counts[this->prediction_history[i]] += 1;
      }

      // Determine the class with the highest average score
      int max_class_index = 0;
      for (int i = 1; i < 3; ++i)
      {
        if (class_counts[i] > class_counts[max_class_index])
        {
          max_class_index = i;
        }
      }

      return max_class_index;
#else
      // Update EMA for each class
      double new_values[3] = {0};
      new_values[max_index] = 1;

      for (int i = 0; i < 3; ++i)
      {
        this->current_predictions[i] =
            this->ema_alpha * new_values[i] + (1 - this->ema_alpha) * this->current_predictions[i];
      }

      // Determine the class with the highest EMA value
      int max_class_index = 0;
      for (int i = 1; i < 3; ++i)
      {
        if (this->current_predictions[i] > this->current_predictions[max_class_index])
        {
          max_class_index = i;
        }
      }

      return max_class_index;
#endif
    }
  } // namespace litter_robot_presence_detector
} // namespace esphome
#endif
