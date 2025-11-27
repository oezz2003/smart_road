# Smart Road Traffic System 🚦
# نظام الطريق الذكي

[English](#english) | [العربية](#arabic)

---

<a name="english"></a>
## 🇬🇧 English Section

### Overview
This project is a Smart Traffic Light System using Computer Vision and IoT. It monitors traffic density in 4 directions (N, S, E, W) using a camera and dynamically adjusts signal timings to optimize traffic flow. Data is sent to ESP32 controllers via MQTT.

### 📂 File Structure
- **`vision_select_and_count.py`**: Handles camera input, allows ROI selection, and counts vehicles using background subtraction.
- **`algo_two_phase.py`**: Contains the logic for calculating traffic signal timings (Green/Red duration) based on vehicle counts.
- **`iot_publisher.py`**: The main script that integrates vision and logic, then publishes commands to the MQTT broker.
- **`test_iot.py`**: A simple script to test the MQTT connection without running the full vision system.
- **`requirements.txt`**: Lists all Python libraries required to run the project.
- **`roi_config.json`**: Stores the coordinates of the selected traffic zones (created automatically).

### Prerequisites
- Python 3.8+
- A webcam connected to your PC.
- Internet connection (for MQTT).

### Installation

1.  **Install Dependencies:**
    Open your terminal/command prompt in the project folder and run:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: If you encounter OpenCV errors, ensure you have `opencv-contrib-python` installed.*

### Usage Instructions

#### Step 1: Configure Vision (ROI Selection)
Before running the system, you must define the Regions of Interest (ROIs) for the 4 directions.

1.  Run the vision setup script:
    ```bash
    python vision_select_and_count.py
    ```
2.  A camera window will open. Follow the on-screen prompts in the terminal:
    -   Select the **North (N)** area and press `ENTER`.
    -   Select the **South (S)** area and press `ENTER`.
    -   Select the **East (E)** area and press `ENTER`.
    -   Select the **West (W)** area and press `ENTER`.
3.  The configuration will be saved to `roi_config.json`.

#### Step 2: Run the System
To start monitoring traffic and controlling signals:

1.  Run the main publisher script:
    ```bash
    python iot_publisher.py
    ```
2.  The system will:
    -   Open the camera and count cars in the defined ROIs.
    -   Calculate optimal Green/Red times.
    -   Publish commands to the MQTT broker (Topic: `signals/cycle`).

### Troubleshooting
-   **OpenCV Error:** If you see an error about `cvShowImage` or UI, run:
    ```bash
    pip uninstall opencv-python opencv-python-headless
    pip install opencv-contrib-python
    ```
-   **Reset ROIs:** To re-select areas, simply delete `roi_config.json` and run Step 1 again.

---

<a name="arabic"></a>
## 🇪🇬 القسم العربي

### نبذة عن المشروع
هذا المشروع عبارة عن نظام إشارات مرور ذكي يعتمد على الرؤية الحاسوبية (Computer Vision) وإنترنت الأشياء (IoT). يقوم النظام بمراقبة كثافة السيارات في 4 اتجاهات (شمال، جنوب، شرق، غرب) باستخدام الكاميرا، ويقوم بضبط أوقات الإشارة تلقائياً لتقليل الازدحام. يتم إرسال الأوامر لوحدات التحكم (ESP32) عبر بروتوكول MQTT.

### 📂 شرح الملفات
- **`vision_select_and_count.py`**: مسؤول عن تشغيل الكاميرا، تحديد مناطق الطريق، وعد السيارات.
- **`algo_two_phase.py`**: يحتوي على الخوارزمية التي تحسب الوقت المناسب للإشارة الخضراء والحمراء بناءً على عدد السيارات.
- **`iot_publisher.py`**: الملف الرئيسي الذي يربط بين الرؤية والخوارزمية ويرسل الأوامر عبر الإنترنت (MQTT).
- **`test_iot.py`**: كود بسيط لاختبار الاتصال بالسيرفر دون تشغيل الكاميرا.
- **`requirements.txt`**: قائمة بالمكتبات اللازمة لتشغيل المشروع.
- **`roi_config.json`**: ملف يتم إنشاؤه تلقائياً لحفظ إحداثيات المناطق التي قمت بتحديدها.

### المتطلبات
- بايثون 3.8 أو أحدث.
- كاميرا ويب متصلة بالكمبيوتر.
- اتصال بالإنترنت (للاتصال بسيرفر MQTT).

### التثبيت

1.  **تثبيت المكتبات المطلوبة:**
    افتح التيرمينال في مجلد المشروع ونفذ الأمر التالي:
    ```bash
    pip install -r requirements.txt
    ```
    *ملاحظة: تأكد من تثبيت `opencv-contrib-python` لتجنب مشاكل واجهة الكاميرا.*

### تعليمات التشغيل

#### الخطوة 1: إعداد الرؤية (تحديد المناطق)
قبل تشغيل النظام، يجب تحديد مناطق الطريق الأربعة (ROIs) التي سيتم مراقبتها.

1.  شغل كود الإعداد:
    ```bash
    python vision_select_and_count.py
    ```
2.  ستظهر نافذة الكاميرا. اتبع التعليمات في التيرمينال:
    -   حدد منطقة **الشمال (N)** بمستطيل ثم اضغط `ENTER`.
    -   حدد منطقة **الجنوب (S)** بمستطيل ثم اضغط `ENTER`.
    -   حدد منطقة **الشرق (E)** بمستطيل ثم اضغط `ENTER`.
    -   حدد منطقة **الغرب (W)** بمستطيل ثم اضغط `ENTER`.
3.  سيتم حفظ الإعدادات تلقائياً في ملف `roi_config.json`.

#### الخطوة 2: تشغيل النظام
لبدء مراقبة المرور والتحكم في الإشارات:

1.  شغل الملف الرئيسي:
    ```bash
    python iot_publisher.py
    ```
2.  سيقوم النظام بـ:
    -   فتح الكاميرا وعد السيارات في المناطق المحددة.
    -   حساب الوقت المناسب للإشارة الخضراء والحمراء.
    -   إرسال الأوامر لسيرفر MQTT (على التوبيك `signals/cycle`).

### حل المشاكل
-   **خطأ OpenCV:** إذا ظهر خطأ يتعلق بـ `cvShowImage` أو الواجهة، نفذ الأوامر التالية لإصلاح المكتبة:
    ```bash
    pip uninstall opencv-python opencv-python-headless
    pip install opencv-contrib-python
    ```
-   **إعادة تحديد المناطق:** إذا أردت تغيير المناطق، قم بحذف ملف `roi_config.json` ثم كرر الخطوة 1.
