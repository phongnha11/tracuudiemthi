import streamlit as st
import gspread
import google.generativeai as genai
import requests
import random
import time
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request

# --- 1. CẤU HÌNH GIAO DIỆN XANH DƯƠNG HIỆN ĐẠI ---
st.set_page_config(
    page_title="Tra Cứu Điểm Thi 2025",
    page_icon="🎓",
    layout="centered"
)

# CSS tùy chỉnh: Màu xanh chủ đạo, bo góc, bóng đổ nhẹ
st.markdown("""
<style>
    /* Ẩn menu mặc định */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Font chữ và màu nền */
    .stApp {
        background-color: #F8F9FA;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* Tiêu đề chính */
    h1 {
        color: #1565C0; /* Xanh đậm */
        text-align: center;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 0px;
    }
    
    /* Caption dưới tiêu đề */
    .stCaption {
        text-align: center;
        color: #546E7A;
        font-size: 1.1em;
        margin-bottom: 20px;
    }

    /* Khung chat tin nhắn */
    .stChatMessage {
        background-color: #FFFFFF;
        border-radius: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        padding: 10px;
        margin-bottom: 10px;
        border: 1px solid #E1E8ED;
    }

    /* Tin nhắn của User */
    .stChatMessage[data-testid="stChatMessage"]:nth-child(odd) {
        background-color: #E3F2FD; /* Xanh nhạt cho user */
        border-right: 4px solid #2196F3;
    }
    
    /* Tin nhắn của Bot */
    .stChatMessage[data-testid="stChatMessage"]:nth-child(even) {
        background-color: #FFFFFF;
        border-left: 4px solid #FF9800; /* Cam điểm nhấn cho bot */
    }

    /* Input box */
    .stChatInput input {
        border-radius: 20px !important;
        border: 2px solid #BBDEFB !important;
    }
    
    /* Hiệu ứng load */
    .stSpinner > div {
        border-top-color: #1565C0 !important;
    }
</style>
""", unsafe_allow_html=True)

# Header giao diện
st.title("🎓 Cổng Tra Cứu Điểm Thi")
st.caption("Trường THPT Phan Bội Châu - Phan Thiết")
st.markdown("---")

# --- 2. CẤU HÌNH DỮ LIỆU ---

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

# Dữ liệu Rubric/Đáp án mẫu (Để AI phân tích lỗi sai)
EXAM_RUBRICS = {
    "toán": "Đáp án trắc nghiệm: 1A 2B 3C... Tự luận: Câu 1 vẽ đồ thị (1đ), Câu 2 phương trình (2đ)...",
    "văn": "Mở bài (0.5), Thân bài (3.0), Kết bài (0.5). Yêu cầu phân tích tâm trạng nhân vật...",
    # Bạn có thể bổ sung thêm rubric chi tiết ở đây
}

# --- 3. HÀM KẾT NỐI (BACKEND) ---

def get_credentials():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)

@st.cache_data(ttl=300)
def get_data():
    try:
        creds = get_credentials()
        client = gspread.authorize(creds)
        # --- THAY URL GOOGLE SHEET CỦA BẠN VÀO ĐÂY ---
        SHEET_URL = "https://docs.google.com/spreadsheets/d/THAY_ID_SHEET_CUA_BAN/edit" 
        return client.open_by_url(SHEET_URL).sheet1.get_all_records()
    except Exception as e:
        st.error(f"❌ Lỗi kết nối dữ liệu: {str(e)}")
        return []

def get_image_data(link):
    """Tải ảnh bảo mật từ Google Drive"""
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

# --- 4. LOGIC XỬ LÝ THÔNG MINH (AI + PYTHON) ---

def handle_local_query(prompt, user_data):
    """Xử lý hiển thị điểm bằng Python (Đã sửa lỗi lặp môn)"""
    p = prompt.lower()
    msg = ""
    link = None
    
    # 1. Hiển thị Bảng điểm Tổng kết
    if "bảng điểm" in p or "tất cả" in p or "tổng kết" in p:
        msg = "📋 **Bảng điểm chi tiết của em:**\n\n"
        processed_cols = set() # Set giúp lọc trùng lặp
        
        for sub_name, cols in SUBJECT_MAP.items():
            score_col = cols[0]
            # Logic: Chỉ in nếu cột đó CHƯA in và CÓ điểm
            if score_col not in processed_cols and user_data.get(score_col):
                msg += f"- {sub_name.title()}: **{user_data[score_col]}**\n"
                processed_cols.add(score_col) # Đánh dấu đã in
        return msg, None

    # 2. Hiển thị điểm từng môn
    found_subject = None
    for sub_name, cols in SUBJECT_MAP.items():
        if sub_name in p:
            found_subject = (sub_name, cols)
            break
    
    if found_subject:
        sub_name, cols = found_subject
        score = user_data.get(cols[0], "Chưa cập nhật")
        
        if any(w in p for w in ["bài làm", "ảnh", "xem bài"]):
            if cols[1] and user_data.get(cols[1]):
                msg = f"📸 Đây là bài làm môn **{sub_name.title()}** của em."
                link = user_data.get(cols[1])
            else:
                msg = f"⚠️ Môn **{sub_name.title()}** hiện chưa có ảnh bài làm."
        elif any(w in p for w in ["điểm", "nhiêu", "có chưa"]):
            msg = f"✅ Điểm môn **{sub_name.title()}** của em là: **{score}**"
            
    return msg, link

def call_gemini_analysis(prompt, user_data, subject_name, image_bytes):
    """Gọi AI phân tích lỗi sai (Kèm ảnh + Rubric)"""
    rubric = EXAM_RUBRICS.get(subject_name, "Chưa có rubric chi tiết.")
    keys = st.secrets["gemini_keys"] # Lấy danh sách key
    genai.configure(api_key=random.choice(keys)) # Xoay vòng key
    model = genai.GenerativeModel('gemini-1.5-flash')

    sys_prompt = f"""
    Bạn là giáo viên bộ môn {subject_name}. Học sinh: {user_data.get('HoTen')}.
    Nhiệm vụ: Xem ảnh bài làm và đối chiếu với RUBRIC sau:
    {rubric}
    
    Câu hỏi của HS: "{prompt}"
    Yêu cầu: Chỉ ra lỗi sai cụ thể, giải thích ngắn gọn, giọng điệu khích lệ.
    """
    try:
        # Gửi Text + Ảnh cho AI
        image_part = {"mime_type": "image/jpeg", "data": image_bytes}
        response = model.generate_content([sys_prompt, image_part])
        return response.text
    except Exception as e:
        return f"⚠️ Thầy/Cô chưa đọc được ảnh lúc này. ({str(e)})"

def call_gemini_chat(prompt, user_data):
    """Chat thông thường (Không ảnh, xoay vòng Key)"""
    keys = st.secrets["gemini_keys"]
    try:
        genai.configure(api_key=random.choice(keys))
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Tạo ngữ cảnh (Đã lọc trùng môn)
        context = ""
        processed = set()
        for sub, cols in SUBJECT_MAP.items():
            if cols[0] not in processed:
                context += f"{sub.title()}: {user_data.get(cols[0], 'N/A')} | "
                processed.add(cols[0])

        sys_prompt = f"""
        Bạn là trợ lý ảo trường THPT Phan Bội Châu. 
        Học sinh: {user_data.get('HoTen')} (Lớp {user_data.get('Lop')}).
        Bảng điểm: {context}
        Câu hỏi: "{prompt}"
        Trả lời thân thiện, ngắn gọn, style Gen Z (dùng emoji).
        """
        response = model.generate_content(sys_prompt)
        return response.text
    except:
        return "Hệ thống đang bận xíu, em hỏi lại sau nha! 🤯"

# --- 5. ĐIỀU KHIỂN LUỒNG CHÍNH (MAIN FLOW) ---

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "👋 Chào em! Nhập **Mã học sinh** để bắt đầu tra cứu nhé."}]
if "step" not in st.session_state: st.session_state.step = "CHECK_ID"

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    avatar = "🤖" if msg["role"] == "assistant" else "🧑‍🎓"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if "image_data" in msg and msg["image_data"]:
            st.image(msg["image_data"], caption="📄 Bài làm chi tiết", use_container_width=True)

# Xử lý nhập liệu
if prompt := st.chat_input("Nhập tin nhắn..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍🎓"): st.write(prompt)

    resp_text = ""
    resp_img_bytes = None
    data_list = get_data()

    # --- CÁC BƯỚC ĐĂNG NHẬP ---
    if st.session_state.step == "CHECK_ID":
        user = next((item for item in data_list if str(item["MaHS"]).upper() == prompt.strip().upper()), None)
        if user:
            st.session_state.temp_user = user
            st.session_state.step = "CHECK_DOB"
            resp_text = f"✅ Chào **{user['HoTen']}**. Vui lòng nhập **Ngày sinh** (dd/mm/yyyy)."
        else: resp_text = "❌ Mã HS không tồn tại. Em kiểm tra lại nhé."

    elif st.session_state.step == "CHECK_DOB":
        if prompt.strip() == str(st.session_state.temp_user["NgaySinh"]).strip():
            st.session_state.step = "CHECK_SECRET"
            resp_text = "🔒 Đúng ngày sinh. Nhập **Số bí mật** để mở khóa."
        else: resp_text = "⛔ Ngày sinh không khớp."

    elif st.session_state.step == "CHECK_SECRET":
        if prompt.strip() == str(st.session_state.temp_user["SoBiMat"]).strip():
            st.session_state.step = "CHAT"
            st.session_state.user_info = st.session_state.temp_user
            # Tự động hiển thị bảng điểm khi login thành công
            intro, _ = handle_local_query("bảng điểm", st.session_state.user_info)
            resp_text = f"🎉 **Đăng nhập thành công!** Chào {st.session_state.user_info['HoTen']} - Lớp {st.session_state.user_info['Lop']}.\n\n{intro}"
            st.balloons()
        else: resp_text = "⛔ Số bí mật sai rồi."

    # --- CHAT & TRA CỨU ---
    elif st.session_state.step == "CHAT":
        user_data = st.session_state.user_info
        
        # 1. Kiểm tra xem có phải yêu cầu PHÂN TÍCH LỖI SAI không?
        is_analysis = any(w in prompt.lower() for w in ["tại sao", "lỗi sai", "phân tích", "chữa bài", "giải thích"])
        current_sub_name = next((sub for sub in SUBJECT_MAP if sub in prompt.lower()), None)

        if is_analysis and current_sub_name:
            cols = SUBJECT_MAP[current_sub_name]
            img_link = user_data.get(cols[1])
            if img_link:
                with st.spinner(f"🤖 Thầy/Cô đang đọc bài {current_sub_name.title()} để phân tích..."):
                    img_bytes = get_image_data(img_link)
                    if img_bytes:
                        resp_text = call_gemini_analysis(prompt, user_data, current_sub_name, img_bytes)
                        resp_img_bytes = img_bytes # Hiện lại ảnh để tiện đối chiếu
                    else:
                        resp_text = "⚠️ Không tải được ảnh bài làm để phân tích."
            else:
                resp_text = f"⚠️ Môn {current_sub_name.title()} chưa có ảnh bài làm."
        
        # 2. Nếu không phải phân tích -> Thử trả lời bằng Python (Tra điểm nhanh)
        else:
            local_msg, local_link = handle_local_query(prompt, user_data)
            if local_msg:
                resp_text = local_msg
                if local_link:
                    with st.spinner("Đang tải ảnh..."):
                        resp_img_bytes = get_image_data(local_link)
            else:
                # 3. Nếu Python bó tay -> Chat AI thông thường
                with st.spinner("🤖 AI đang suy nghĩ..."):
                    resp_text = call_gemini_chat(prompt, user_data)

    # Hiển thị kết quả
    msg_obj = {"role": "assistant", "content": resp_text}
    if resp_img_bytes: msg_obj["image_data"] = resp_img_bytes
    
    st.session_state.messages.append(msg_obj)
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown(resp_text)
        if resp_img_bytes:
            st.image(resp_img_bytes, caption="📄 Bài làm chi tiết", use_container_width=True)
