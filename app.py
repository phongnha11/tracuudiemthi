import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import pandas as pd

# --- 1. CẤU HÌNH & KẾT NỐI ---
st.set_page_config(page_title="Tra cứu điểm thi 2025", page_icon="🎓")

# Ẩn menu mặc định
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stChatMessage {border-radius: 10px; padding: 10px; margin-bottom: 5px;}
</style>
""", unsafe_allow_html=True)

# Lấy Key từ Secrets
try:
    # Cấu hình Google Sheet
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    
    # Cấu hình Gemini
    genai.configure(api_key=st.secrets["gemini_api_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error("⚠️ Lỗi cấu hình! Vui lòng kiểm tra lại file Secrets.")
    st.stop()

# --- 2. HÀM XỬ LÝ DỮ LIỆU ---

@st.cache_data(ttl=600) # Cache dữ liệu 10 phút để đỡ tốn quota đọc Sheet
def get_data():
    try:
        sheet = client.open("Diem_Thi_2025").sheet1 # Thay tên Sheet của bạn vào đây
        data = sheet.get_all_records()
        return data
    except Exception as e:
        st.error(f"Không đọc được dữ liệu: {e}")
        return []

def clean_drive_link(link):
    """Chuyển link Google Drive view sang link preview để hiển thị ảnh"""
    if not link: return None
    if "drive.google.com" in link and "/view" in link:
        # Tách ID từ link: .../d/FILE_ID/view...
        file_id = link.split('/d/')[1].split('/')[0]
        return f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000" # Link thumbnail chất lượng cao
    return link

# Danh sách môn học và mapping cột (Tên hiển thị: (Cột điểm, Cột ảnh))
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
    "Thể dục": ("DiemTD", None), # Môn này bạn không có cột ảnh
    "Quốc phòng": ("DiemQP", None) # Môn này bạn không có cột ảnh
}

# --- 3. LOGIC HỘI THOẠI (STATE MACHINE) ---

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "👋 Chào em! Thầy/Cô là trợ lý ảo tra cứu điểm. Vui lòng nhập **Mã học sinh** để bắt đầu."}]

if "step" not in st.session_state:
    st.session_state.step = "CHECK_ID" # Quy trình: CHECK_ID -> CHECK_DOB -> CHECK_SECRET -> CHAT

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # Nếu có ảnh trong tin nhắn cũ, hiển thị lại (lưu trong field 'image' nếu có)
        if "image" in msg and msg["image"]:
            st.image(msg["image"], caption="Ảnh bài làm/Minh chứng", use_container_width=True)

# --- 4. XỬ LÝ KHI USER NHẬP LIỆU ---
if prompt := st.chat_input("Nhập tin nhắn..."):
    # 4.1 Hiển thị tin nhắn user
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # 4.2 Xử lý logic
    response_text = ""
    response_image = None
    data = get_data()
    
    # --- BƯỚC 1: KIỂM TRA MÃ HS ---
    if st.session_state.step == "CHECK_ID":
        user = next((item for item in data if str(item["MaHS"]).strip().upper() == prompt.strip().upper()), None)
        if user:
            st.session_state.temp_user = user
            st.session_state.step = "CHECK_DOB"
            response_text = f"✅ Tìm thấy học sinh **{user.get('MaHS')}**. Vui lòng nhập **Ngày sinh** (dd/mm/yyyy) để tiếp tục."
        else:
            response_text = "❌ Không tìm thấy Mã HS này trong hệ thống. Vui lòng nhập lại."

    # --- BƯỚC 2: KIỂM TRA NGÀY SINH ---
    elif st.session_state.step == "CHECK_DOB":
        stored_dob = str(st.session_state.temp_user["NgaySinh"]).strip()
        if prompt.strip() == stored_dob:
            st.session_state.step = "CHECK_SECRET"
            response_text = "🔒 Đúng ngày sinh. Để bảo mật tuyệt đối, vui lòng nhập **Số bí mật** (Mã cá nhân) mà giáo viên đã cung cấp."
        else:
            response_text = "⛔ Ngày sinh không khớp. Vui lòng kiểm tra lại định dạng (ví dụ: 15/05/2008)."

    # --- BƯỚC 3: KIỂM TRA SỐ BÍ MẬT ---
    elif st.session_state.step == "CHECK_SECRET":
        stored_secret = str(st.session_state.temp_user["SoBiMat"]).strip()
        if prompt.strip() == stored_secret:
            st.session_state.step = "CHAT"
            st.session_state.current_user = st.session_state.temp_user
            response_text = "🎉 **Xác thực thành công!** Chào mừng em. Em có thể hỏi điểm từng môn hoặc yêu cầu xem bài làm (Ví dụ: 'Xem bài làm Toán')."
        else:
            response_text = "⛔ Số bí mật không đúng."

    # --- BƯỚC 4: TRA CỨU THÔNG TIN (GEMINI) ---
    elif st.session_state.step == "CHAT":
        user_data = st.session_state.current_user
        
        # Chuẩn bị dữ liệu ngữ cảnh cho Gemini
        data_context = "Bảng điểm của học sinh:\n"
        for subject, cols in SUBJECT_MAP.items():
            score_col = cols[0]
            img_col = cols[1]
            score = user_data.get(score_col, "Chưa có")
            
            # Kiểm tra xem có ảnh không
            has_img = "Có" if (img_col and user_data.get(img_col)) else "Không"
            img_link = user_data.get(img_col, "") if img_col else ""
            
            data_context += f"- Môn {subject}: {score} điểm (Link ảnh bài làm: {img_link})\n"

        # Tạo Prompt
        system_prompt = f"""
        Bạn là trợ lý tra cứu điểm thi thân thiện.
        Dữ liệu học sinh đang tra cứu:
        {data_context}
        
        Người dùng hỏi: "{prompt}"
        
        Yêu cầu:
        1. Trả lời chính xác điểm số từ dữ liệu trên.
        2. Nếu người dùng muốn xem "bài làm", "ảnh", "bằng chứng" của một môn:
           - Kiểm tra xem có Link ảnh không.
           - Nếu có, hãy trả lời câu: "Đây là bài làm môn [Tên môn] của em: [Link ảnh]"
           - Nếu không có, hãy báo là chưa cập nhật ảnh.
        3. Luôn động viên học sinh.
        """

        try:
            gemini_response = model.generate_content(system_prompt)
            response_text = gemini_response.text
            
            # Tách link ảnh ra để hiển thị đẹp (nếu Gemini trả về link)
            words = response_text.split()
            for word in words:
                if "http" in word:
                    # Nếu phát hiện link, thử convert sang link ảnh
                    potential_img = clean_drive_link(word.strip('.,;()[]'))
                    if potential_img:
                        response_image = potential_img
                        # Có thể chọn ẩn link gốc trong text đi nếu muốn, ở đây ta cứ để nguyên
        except Exception as e:
            response_text = f"⚠️ Lỗi kết nối AI: {str(e)}"

    # 4.3 Phản hồi lại User
    msg_obj = {"role": "assistant", "content": response_text}
    if response_image:
        msg_obj["image"] = response_image # Lưu ảnh vào lịch sử chat
        
    st.session_state.messages.append(msg_obj)
    
    with st.chat_message("assistant"):
        st.markdown(response_text)
        if response_image:
            st.image(response_image, caption="Bài làm chi tiết", use_container_width=True)


