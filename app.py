import streamlit as st
import gspread
import google.generativeai as genai
import requests
import google.auth.transport.requests
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request

# --- 1. CẤU HÌNH GIAO DIỆN & TRANG ---
st.set_page_config(
    page_title="Tra Cứu Điểm Thi 2025",
    page_icon="🏫",
    layout="centered"
)

# CSS tùy chỉnh để giao diện đẹp hơn, ẩn menu mặc định
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stChatMessage {
        border-radius: 15px;
        padding: 10px;
        margin-bottom: 10px;
    }
    /* Tạo hiệu ứng cho tiêu đề */
    h1 {
        color: #2E86C1;
        text-align: center;
        font-family: 'Helvetica', sans-serif;
    }
</style>
""", unsafe_allow_html=True)

# Tiêu đề sinh động
st.title("🏫 Cổng Tra Cứu Điểm Thi")
st.caption("🚀 Hệ thống hỗ trợ bởi AI - Trả lời thắc mắc & Xem bài làm chi tiết")

# --- 2. KẾT NỐI DỊCH VỤ (Google Sheets & Drive & Gemini) ---

# Hàm lấy Credentials an toàn
def get_credentials():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)

# Kết nối Gemini
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    model = genai.GenerativeModel('gemini-2.5-flash') # Dùng bản Flash cho nhanh
except Exception as e:
    st.error("⚠️ Lỗi cấu hình API Key Gemini. Vui lòng kiểm tra lại Secrets.")
    st.stop()

# Hàm lấy dữ liệu từ Google Sheet (Dùng URL để tránh lỗi tìm tên)
@st.cache_data(ttl=300) # Cache 5 phút
def get_data():
    try:
        creds = get_credentials()
        client = gspread.authorize(creds)
        # --- BẠN HÃY THAY LINK GOOGLE SHEET CỦA BẠN VÀO DÒNG DƯỚI ---
        SHEET_URL = "https://docs.google.com/spreadsheets/d/1C36wek7yVD28NHWGBuqvi_1wHoA0Ysa22dQ6VkOm6dg/edit" 
        
        sheet = client.open_by_url(SHEET_URL).sheet1
        return sheet.get_all_records()
    except Exception as e:
        st.error(f"❌ Không kết nối được dữ liệu điểm: {str(e)}")
        return []

# Hàm tải ảnh Bảo Mật từ Drive (Không cần Public ảnh)
def get_image_data(link):
    if not link: return None
    
    # Lấy ID file từ link
    file_id = None
    if "/d/" in link:
        file_id = link.split('/d/')[1].split('/')[0]
    elif "id=" in link:
        file_id = link.split('id=')[1].split('&')[0]
    
    if not file_id: return None

    # Lấy Token truy cập
    creds = get_credentials()
    try:
        # Refresh token nếu cần
        creds.refresh(Request())
        token = creds.token
    except:
        token = creds.token 

    # Gọi API Drive tải ảnh
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.content
    except:
        pass
    return None

# --- 3. CẤU TRÚC DỮ LIỆU MÔN HỌC ---
# Mapping: Tên môn -> (Tên cột điểm, Tên cột ảnh)
SUBJECT_MAP = {
    "Toán": ("DiemToan", "AnhToan"),
    "Lý": ("DiemLy", "AnhLy"),
    "Hóa": ("DiemHoa", "AnhHoa"),
    "Sinh": ("DiemSinh", "AnhSinh"),
    "Văn": ("DiemVan", "AnhVan"),
    "Sử": ("DiemSu", "AnhSu"),
    "Địa": ("DiemDia", "AnhDia"),
    "KT&PL": ("DiemKT&PL", "AnhKT&PL"),
    "Ngoại Ngữ": ("DiemNN", "AnhNN"),
    "Tin học": ("DiemTin", "AnhTin"),
    "Công nghệ": ("DiemCN", "AnhCN"),
    "Thể dục": ("DiemTD", None),
    "Quốc phòng": ("DiemQP", None)
}

# --- 4. QUẢN LÝ TRẠNG THÁI (STATE) ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "👋 Chào em! Nhập **Mã học sinh** để thầy/cô giúp em tra cứu nhé."}
    ]
if "step" not in st.session_state:
    st.session_state.step = "CHECK_ID" # CHECK_ID -> CHECK_DOB -> CHECK_SECRET -> CHAT
if "user_info" not in st.session_state:
    st.session_state.user_info = None

# --- 5. GIAO DIỆN CHAT CHÍNH ---

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    # Chọn Avatar: Bot dùng icon robot, User dùng icon học sinh
    avatar = "🤖" if msg["role"] == "assistant" else "🧑‍🎓"
    
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        # Nếu tin nhắn cũ có ảnh, hiển thị lại
        if "image_data" in msg and msg["image_data"]:
            st.image(msg["image_data"], caption="📸 Ảnh bài làm", use_container_width=True)

# Xử lý nhập liệu
if prompt := st.chat_input("Nhập tin nhắn..."):
    # 1. Hiển thị tin nhắn người dùng
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.write(prompt)

    # 2. Chuẩn bị biến trả về
    response_text = ""
    response_image_link = None
    response_image_bytes = None # Dữ liệu ảnh dạng bytes để hiển thị
    
    # Lấy dữ liệu mới nhất
    data_list = get_data()

    # --- LOGIC XỬ LÝ TỪNG BƯỚC ---
    
    # Bước 1: Kiểm tra Mã HS
    if st.session_state.step == "CHECK_ID":
        # Tìm không phân biệt hoa thường
        user = next((item for item in data_list if str(item["MaHS"]).strip().upper() == prompt.strip().upper()), None)
        
        if user:
            st.session_state.temp_user = user
            st.session_state.step = "CHECK_DOB"
            response_text = f"✅ Đã tìm thấy: **{user['MaHS']}**. Vui lòng nhập **Ngày sinh** (dd/mm/yyyy) để xác thực."
        else:
            response_text = "❌ Không tìm thấy Mã HS này. Em kiểm tra lại nhé!"

    # Bước 2: Kiểm tra Ngày Sinh
    elif st.session_state.step == "CHECK_DOB":
        real_dob = str(st.session_state.temp_user["NgaySinh"]).strip()
        if prompt.strip() == real_dob:
            st.session_state.step = "CHECK_SECRET"
            response_text = "🔒 Đúng ngày sinh. Bước cuối cùng: Nhập **Số bí mật** giáo viên đã cấp."
        else:
            response_text = "⛔ Ngày sinh không khớp. Hãy nhập đúng định dạng (VD: 15/05/2008)."

    # Bước 3: Kiểm tra Số Bí Mật
    elif st.session_state.step == "CHECK_SECRET":
        real_secret = str(st.session_state.temp_user["SoBiMat"]).strip()
        if prompt.strip() == real_secret:
            st.session_state.step = "CHAT"
            st.session_state.user_info = st.session_state.temp_user
            response_text = f"🎉 **Xác thực thành công!** Chào mừng **{st.session_state.user_info['HoTen']}** (Lớp {st.session_state.user_info.get('Lop', '')}).\n\nEm muốn hỏi điểm môn nào, hoặc xem bài làm môn gì?"
            st.balloons() # Hiệu ứng pháo hoa chúc mừng
        else:
            response_text = "⛔ Số bí mật không đúng."

    # Bước 4: Chat với AI (Gemini)
    elif st.session_state.step == "CHAT":
        user_data = st.session_state.user_info
        
        # Tạo ngữ cảnh dữ liệu cho AI
        context_str = "Bảng điểm chi tiết:\n"
        for sub, cols in SUBJECT_MAP.items():
            score = user_data.get(cols[0], "N/A")
            has_img = "Có link ảnh" if user_data.get(cols[1]) else "Chưa có ảnh"
            img_link = user_data.get(cols[1], "")
            context_str += f"- {sub}: {score} điểm (Trạng thái ảnh: {has_img}, Link: {img_link})\n"

        # Tạo Prompt hệ thống
        system_prompt = f"""
        Bạn là trợ lý ảo trường học thân thiện, vui tính. 
        Người dùng là học sinh tên: {user_data.get('HoTen')}.
        
        Dữ liệu điểm số:
        {context_str}
        
        Yêu cầu:
        1. Trả lời câu hỏi dựa trên dữ liệu. Giọng điệu khích lệ, dùng emoji.
        2. Nếu học sinh muốn xem "bài làm", "ảnh", "minh chứng" -> Hãy tìm Link ảnh trong dữ liệu và in ra link đó trong câu trả lời.
        3. Nếu điểm thấp, hãy động viên. Nếu điểm cao, hãy khen ngợi.
        
        Câu hỏi của học sinh: "{prompt}"
        """

        try:
            # Gọi Gemini
            ai_resp = model.generate_content(system_prompt)
            response_text = ai_resp.text
            
            # Tách Link ảnh từ câu trả lời (nếu có)
            words = response_text.split()
            for word in words:
                clean_word = word.strip('.,;()[]<>')
                if "http" in clean_word and "drive.google.com" in clean_word:
                    response_image_link = clean_word
                    break
        except Exception as e:
            response_text = "Hệ thống đang bận một chút, em hỏi lại nhé!"
            print(e)

    # 3. Phản hồi ra giao diện
    
    # Nếu có link ảnh, tải ảnh về dạng bytes để hiển thị an toàn
    if response_image_link:
        with st.spinner("Đang tải bài làm từ kho dữ liệu nhà trường..."):
            response_image_bytes = get_image_data(response_image_link)
            if not response_image_bytes:
                response_text += "\n\n(⚠️ Thầy/Cô chưa cấp quyền xem ảnh này hoặc ảnh chưa cập nhật)"

    # Lưu vào lịch sử chat
    msg_obj = {"role": "assistant", "content": response_text}
    if response_image_bytes:
        msg_obj["image_data"] = response_image_bytes
    
    st.session_state.messages.append(msg_obj)

    # Render tin nhắn vừa xong
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown(response_text)
        if response_image_bytes:
            st.image(response_image_bytes, caption="📸 Bài làm chi tiết", use_container_width=True)

