import streamlit as st
import gspread
import google.generativeai as genai
import requests
import random
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request

# --- 1. CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title="Tra Cứu Điểm Thi 2025", page_icon="🏫", layout="centered")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stChatMessage {border-radius: 15px; padding: 10px; margin-bottom: 10px;}
    h1 {color: #2E86C1; text-align: center; font-family: 'Helvetica', sans-serif;}
</style>
""", unsafe_allow_html=True)

st.title("🏫 Cổng Tra Cứu Điểm Thi")
st.caption("🚀 Hệ thống tra cứu thông minh: Nhanh chóng - Chính xác - Bảo mật")

# --- 2. CẤU HÌNH DỮ LIỆU & KẾT NỐI ---

# Mapping Môn học -> (Cột Điểm, Cột Link Ảnh)
SUBJECT_MAP = {
    "toán": ("DiemToan", "AnhToan"),
    "văn": ("DiemVan", "AnhVan"),
    "ngữ văn": ("DiemVan", "AnhVan"),
    "lý": ("DiemLy", "AnhLy"),
    "vật lý": ("DiemLy", "AnhLy"),
    "hóa": ("DiemHoa", "AnhHoa"),
    "hóa học": ("DiemHoa", "AnhHoa"),
    "sinh": ("DiemSinh", "AnhSinh"),
    "sinh học": ("DiemSinh", "AnhSinh"),
    "sử": ("DiemSu", "AnhSu"),
    "lịch sử": ("DiemSu", "AnhSu"),
    "địa": ("DiemDia", "AnhDia"),
    "địa lý": ("DiemDia", "AnhDia"),
    "anh": ("DiemNN", "AnhNN"),
    "tiếng anh": ("DiemNN", "AnhNN"),
    "ngoại ngữ": ("DiemNN", "AnhNN"),
    "gdcd": ("DiemKT&PL", "AnhKT&PL"),
    "kt&pl": ("DiemKT&PL", "AnhKT&PL"),
    "tin": ("DiemTin", "AnhTin"),
    "tin học": ("DiemTin", "AnhTin"),
    "công nghệ": ("DiemCN", "AnhCN"),
    "thể dục": ("DiemTD", None),
    "quốc phòng": ("DiemQP", None)
}

def get_credentials():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)

@st.cache_data(ttl=300)
def get_data():
    try:
        creds = get_credentials()
        client = gspread.authorize(creds)
        # THAY URL CỦA BẠN VÀO ĐÂY
        SHEET_URL = "https://docs.google.com/spreadsheets/d/1C36wek7yVD28NHWGBuqvi_1wHoA0Ysa22dQ6VkOm6dg/edit" 
        return client.open_by_url(SHEET_URL).sheet1.get_all_records()
    except Exception as e:
        st.error(f"❌ Lỗi kết nối dữ liệu: {str(e)}")
        return []

def get_image_data(link):
    if not link: return None
    file_id = None
    if "/d/" in link: file_id = link.split('/d/')[1].split('/')[0]
    elif "id=" in link: file_id = link.split('id=')[1].split('&')[0]
    if not file_id: return None

    creds = get_credentials()
    try:
        creds.refresh(Request())
        token = creds.token
    except:
        token = creds.token 

    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.content if response.status_code == 200 else None
    except:
        return None

# --- 3. LOGIC XỬ LÝ THÔNG MINH (HYBRID) ---

def handle_local_query(prompt, user_data):
    """Xử lý câu hỏi điểm bằng Python (Không tốn API Key)"""
    p = prompt.lower()
    msg = ""
    link = None
    
    # Trường hợp 1: Hỏi "bảng điểm" hoặc "tất cả điểm"
    if "bảng điểm" in p or "tất cả" in p or "tổng kết" in p:
        msg = "📋 **Bảng điểm chi tiết của em:**\n\n"
        for key, val in SUBJECT_MAP.items():
            # Chỉ lấy tên môn ngắn gọn (key có độ dài < 10 để lọc bớt từ đồng nghĩa dài)
            if len(key) < 10 and user_data.get(val[0]): 
                msg += f"- {key.capitalize()}: **{user_data[val[0]]}**\n"
        return msg, None

    # Trường hợp 2: Hỏi điểm từng môn
    # Quét xem trong câu hỏi có tên môn nào không
    found_subject = None
    for sub_name, cols in SUBJECT_MAP.items():
        if sub_name in p:
            found_subject = (sub_name, cols)
            break
    
    if found_subject:
        sub_name, cols = found_subject
        score = user_data.get(cols[0], "Chưa có")
        
        # Nếu hỏi "bài làm" hoặc "ảnh"
        if "bài làm" in p or "ảnh" in p or "xem bài" in p:
            if cols[1] and user_data.get(cols[1]):
                msg = f"📸 Đây là bài làm môn **{sub_name.capitalize()}** của em."
                link = user_data.get(cols[1])
            else:
                msg = f"Môn **{sub_name.capitalize()}** hiện chưa cập nhật ảnh bài làm em nhé."
        
        # Nếu hỏi "điểm"
        elif "điểm" in p or "nhiêu" in p or "có chưa" in p:
            msg = f"Điểm môn **{sub_name.capitalize()}** của em là: **{score}**"
            
    return msg, link

def call_gemini_rotated(prompt, user_data):
    """Gọi AI với cơ chế xoay vòng Key"""
    # 1. Lấy danh sách key và chọn ngẫu nhiên
    keys = st.secrets["gemini_keys"]
    selected_key = random.choice(keys)
    
    try:
        # 2. Cấu hình AI
        genai.configure(api_key=selected_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 3. Tạo ngữ cảnh
        context = "Bảng điểm:\n"
        for sub, cols in SUBJECT_MAP.items():
            if len(sub) < 10: # Lấy đại diện tên môn
                context += f"- {sub}: {user_data.get(cols[0], 'N/A')} (Link ảnh: {user_data.get(cols[1], '')})\n"
                
        sys_prompt = f"""
        Bạn là trợ lý ảo trường học. Học sinh tên: {user_data.get('HoTen')}.
        Dữ liệu: {context}
        Câu hỏi: "{prompt}"
        Yêu cầu: Trả lời thân thiện, ngắn gọn. Nếu học sinh hỏi cách học tập, hãy đưa ra lời khuyên. 
        Nếu câu trả lời có chứa link ảnh bài làm, hãy in link đó ra.
        """
        
        response = model.generate_content(sys_prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Hệ thống đang quá tải, em vui lòng thử lại sau giây lát. (Lỗi: {str(e)})"

# --- 4. GIAO DIỆN CHÍNH ---

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "👋 Chào em! Nhập **Mã học sinh** để thầy/cô giúp em tra cứu nhé."}]
if "step" not in st.session_state: st.session_state.step = "CHECK_ID"

# Hiển thị chat
for msg in st.session_state.messages:
    avatar = "🤖" if msg["role"] == "assistant" else "🧑‍🎓"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if "image_data" in msg and msg["image_data"]:
            st.image(msg["image_data"], caption="📸 Bài làm chi tiết", use_container_width=True)

# Xử lý nhập liệu
if prompt := st.chat_input("Nhập tin nhắn..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍🎓"): st.write(prompt)

    resp_text = ""
    resp_img_bytes = None
    data_list = get_data()

    # --- LOGIC XÁC THỰC (Giữ nguyên như cũ) ---
    if st.session_state.step == "CHECK_ID":
        user = next((item for item in data_list if str(item["MaHS"]).upper() == prompt.strip().upper()), None)
        if user:
            st.session_state.temp_user = user
            st.session_state.step = "CHECK_DOB"
            resp_text = f"✅ Xin chào **{user['HoTen']}**. Vui lòng nhập **Ngày sinh** (dd/mm/yyyy)."
        else: resp_text = "❌ Không tìm thấy Mã HS."

    elif st.session_state.step == "CHECK_DOB":
        if prompt.strip() == str(st.session_state.temp_user["NgaySinh"]).strip():
            st.session_state.step = "CHECK_SECRET"
            resp_text = "🔒 Đúng ngày sinh. Nhập **Số bí mật** để vào hệ thống."
        else: resp_text = "⛔ Ngày sinh không khớp."

    elif st.session_state.step == "CHECK_SECRET":
        if prompt.strip() == str(st.session_state.temp_user["SoBiMat"]).strip():
            st.session_state.step = "CHAT"
            st.session_state.user_info = st.session_state.temp_user
            # Tự động hiển thị bảng điểm ngay khi đăng nhập thành công
            intro_msg, _ = handle_local_query("bảng điểm", st.session_state.user_info)
            resp_text = f"🎉 **Đăng nhập thành công!**\n\n{intro_msg}\nEm cần hỏi thêm gì không?"
            st.balloons()
        else: resp_text = "⛔ Số bí mật sai."

    # --- LOGIC CHAT (PHẦN QUAN TRỌNG NHẤT) ---
    elif st.session_state.step == "CHAT":
        user_data = st.session_state.user_info
        
        # CÁCH 1: Dùng Python xử lý trước (Ưu tiên số 1)
        local_msg, local_link = handle_local_query(prompt, user_data)
        
        if local_msg:
            # Nếu Python trả lời được -> Dùng luôn
            resp_text = local_msg
            img_link_to_load = local_link
        else:
            # CÁCH 2: Nếu Python bó tay -> Gọi AI (Xoay vòng Key)
            with st.spinner("🤖 AI đang suy nghĩ..."):
                resp_text = call_gemini_rotated(prompt, user_data)
                # Tách link ảnh từ lời AI (nếu có)
                img_link_to_load = None
                words = resp_text.split()
                for w in words:
                    cln = w.strip('.,;()[]')
                    if "http" in cln and "drive" in cln:
                        img_link_to_load = cln
                        break

        # Tải ảnh nếu có link
        if img_link_to_load:
            resp_img_bytes = get_image_data(img_link_to_load)

    # Hiển thị kết quả
    msg_obj = {"role": "assistant", "content": resp_text}
    if resp_img_bytes: msg_obj["image_data"] = resp_img_bytes
    
    st.session_state.messages.append(msg_obj)
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown(resp_text)
        if resp_img_bytes:
            st.image(resp_img_bytes, caption="📸 Bài làm", use_container_width=True)
