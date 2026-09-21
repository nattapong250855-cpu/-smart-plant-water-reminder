import os
import json
import time
from datetime import datetime, timedelta
import streamlit as st
from PIL import Image
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------
# 1. การตั้งค่าหน้าจอ Streamlit (Config Page)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Smart Plant Water Reminder",
    page_icon="🌱",
    layout="centered"
)

# -----------------------------------------------------------------------------
# 2. ฟังก์ชันประมวลผลรูปภาพด้วย Gemini API (พร้อม resize รูป + fallback หลายโมเดล)
# -----------------------------------------------------------------------------
def analyze_plant(image: Image.Image, api_key: str) -> dict:
    """ส่งรูปภาพพร้อม Prompt ให้ Gemini วิเคราะห์ และคืนค่าเป็น Python Dictionary"""
    client = genai.Client(api_key=api_key)

    # ย่อขนาดรูปก่อนส่ง ป้องกันไฟล์ใหญ่เกินไปทำให้ timeout/error
    max_size = (1024, 1024)
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail(max_size, Image.LANCZOS)

    prompt = """
    คุณเป็นผู้เชี่ยวชาญด้านพฤกษศาสตร์ การเกษตร และการดูแลไม้ประดับ/ผักสวนครัวแปลงเล็ก

    โปรดวิเคราะห์รูปภาพพืชที่แนบมานี้อย่างละเอียด โดยเน้นสังเกตชนิดพืช สภาพใบ ลำต้น และความชื้นของหน้าดิน จากนั้นให้ตอบกลับในรูปแบบ JSON ภาษาไทย โดยมีโครงสร้าง Schema ตามนี้เท่านั้น:

    {
      "plant_name": "ชื่อพืช (เช่น พริกขี้หนู, กะเพรา, พลูด่าง, ลิ้นมังกร)",
      "plant_type": "ระบุประเภทระหว่าง 'ผักสวนครัว' หรือ 'ไม้ประดับ'",
      "health_analysis": "ประเมินสุขภาพพืชและหน้าดินจากภาพ (เช่น ดินแห้งหน้าแตก ใบเริ่มเหี่ยว หรือ สุขภาพดี ดินชื้นพอดี)",
      "pest_or_disease": "ระบุโรคพืชหรือศัตรูพืชที่พบเบื้องต้น (ถ้าไม่มีให้ระบุ 'ปกติไม่พบศัตรูพืช')",
      "water_interval_days": 3,
      "watering_instructions": "คำแนะนำการรดน้ำสั้นๆ (เช่น รดน้ำให้ชุ่มโคนต้นทุกๆ 3 วัน เช้าหรือเย็น)",
      "sunlight_requirement": "ความต้องการแสงแดด (เช่น แดดจัดครึ่งวัน, แดดรำไร หรือ เลี้ยงในร่มได้)",
      "care_tips": "เทคนิคการดูแลเพิ่มเติม เช่น การใส่ปุ๋ยบำรุง หรือการตัดแต่งกิ่ง"
    }

    หมายเหตุสำหรับค่า "water_interval_days": ต้องใส่เฉพาะตัวเลขจำนวนเต็มเท่านั้น (เช่น 1, 2, 3 หรือ 7)
    """

    # ไล่ลองหลายโมเดล ถ้าตัวไหนเจอ 503 (โหลดสูง) จะสลับไปตัวถัดไปอัตโนมัติ
    models_to_try = ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-3-flash-preview"]
    response = None
    last_error = None

    for model_name in models_to_try:
        for attempt in range(2):  # ลอง 2 ครั้งต่อโมเดล
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[image, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                break  # สำเร็จแล้ว ออกจาก loop ครั้งนี้
            except Exception as e:
                last_error = e
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    time.sleep(3)
                    continue
                else:
                    raise  # error อื่นที่ไม่ใช่ 503 ให้โยนออกทันที
        if response is not None:
            break  # โมเดลนี้สำเร็จแล้ว ไม่ต้องลองโมเดลถัดไป

    if response is None:
        raise last_error

    return json.loads(response.text)


# -----------------------------------------------------------------------------
# 3. ส่วนการจัดวางหน้าจอ UI (Streamlit Layout)
# -----------------------------------------------------------------------------
st.title("🌱 Smart Plant Water Reminder")
st.subheader("ระบบประเมินสุขภาพและแจ้งเตือนการรดน้ำผักสวนครัว & ไม้ประดับ")
st.write("ถ่ายรูปหรืออัปโหลดรูปภาพกระถางต้นไม้/แปลงผัก เพื่อให้ AI วิเคราะห์การดูแลและตั้งเวลาเตือนรดน้ำ")

st.divider()

# Sidebar: สำหรับกรอก API Key
with st.sidebar:
    st.header("⚙️ การตั้งค่า")
    api_key_input = st.text_input(
        "กรอก Gemini API Key:",
        type="password",
        help="ขอ API Key ฟรีได้ที่ https://aistudio.google.com"
    )
    # ดึงค่าจาก Environment Variable หรือ Secrets หากไม่ได้กรอกใน Sidebar
    api_key = api_key_input or os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", "")

# เลือกวิธีป้อนรูปภาพ (อัปโหลด หรือ ใช้กล้องถ่าย)
input_option = st.radio(
    "เลือกวิธีการนำเข้ารถภาพ:",
    ["📤 อัปโหลดไฟล์รูปภาพ", "📷 ถ่ายรูปจากกล้อง"],
    horizontal=True
)

uploaded_file = None
if input_option == "📤 อัปโหลดไฟล์รูปภาพ":
    uploaded_file = st.file_uploader("เลือกรูปถ่ายต้นไม้/ผักสวนครัว (JPG, PNG)", type=["jpg", "jpeg", "png"])
else:
    uploaded_file = st.camera_input("ถ่ายรูปต้นไม้หรือแปลงผัก")

# -----------------------------------------------------------------------------
# 4. ส่วนการประมวลผลเมื่อมีรูปภาพป้อนเข้ามา
# -----------------------------------------------------------------------------
if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="รูปภาพที่นำเข้า", use_container_width=True)

    if st.button("🔍 วิเคราะห์และคำนวณวันรดน้ำ", type="primary"):
        if not api_key:
            st.error("❌ กรุณากรอก Gemini API Key ที่ Sidebar ฝั่งซ้ายก่อนเริ่มใช้งาน")
        else:
            with st.spinner("🤖 AI กำลังสแกนความชื้นดิน สุขภาพใบ และประมวลผลคำแนะนำ..."):
                try:
                    # เรียกใช้งานฟังก์ชัน Gemini
                    result = analyze_plant(image, api_key)

                    # คำนวณวันรดน้ำรอบถัดไป
                    today = datetime.now()
                    interval_days = int(result.get("water_interval_days", 1))
                    next_water_date = today + timedelta(days=interval_days)

                    st.success("✅ วิเคราะห์ข้อมูลสำเร็จ!")
                    st.divider()

                    # สรุปผลลัพธ์หลักด้วย Card Metric
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(label="ชื่อพืช", value=result.get("plant_name", "ไม่ระบุ"))
                    with col2:
                        st.metric(label="ประเภท", value=result.get("plant_type", "ไม่ระบุ"))
                    with col3:
                        st.metric(label="รดน้ำทุกๆ", value=f"{interval_days} วัน")

                    # การ์ดแจ้งเตือนกำหนดการรดน้ำ
                    st.warning(
                        f"📅 **กำหนดการรดน้ำครั้งถัดไป:** วันที่ {next_water_date.strftime('%d/%m/%Y')} "
                        f"(อีก {interval_days} วันนับจากวันนี้)"
                    )

                    # แสดงรายละเอียดผลวิเคราะห์เพิ่มเติม
                    st.subheader("📋 รายละเอียดการวิเคราะห์สภาพพืช")
                    st.write(f"**🧐 สุขภาพพืชและหน้าดิน:** {result.get('health_analysis')}")
                    st.write(f"**🐛 โรคพืช/ศัตรูพืชที่พบ:** {result.get('pest_or_disease')}")
                    st.write(f"**💧 วิธีการรดน้ำ:** {result.get('watering_instructions')}")
                    st.write(f"**☀️ แสงแดดที่ต้องการ:** {result.get('sunlight_requirement')}")
                    st.write(f"**💡 คำแนะนำเพิ่มเติม:** {result.get('care_tips')}")

                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการประมวลผล: {e}")
