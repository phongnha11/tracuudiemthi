import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# 1. CẤU HÌNH TRANG (Để ẩn menu mặc định của Streamlit cho đẹp khi nhúng)
st.set_page_config(page_title="Tra cứu điểm", layout="centered")
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# 2. KẾT NỐI GOOGLE SHEETS (Dùng st.secrets để bảo mật key)
def get_data_from_sheet():
    # Lấy thông tin key từ Secrets của Streamlit Cloud
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    
    # Mở sheet theo tên hoặc ID
    sheet = client.open("Diem_Thi_2025").sheet1 
    data = sheet.get_all_records() # Trả về list of dicts
    return data

# 3. LOGIC HỘI THOẠI (State Management)
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Chào em! Vui lòng nhập Mã học sinh để tra cứu."}]
if "step" not in st.session_state:
    st.session_state.step = "CHECK_ID" # CHECK_ID -> CHECK_DOB -> CHAT

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Xử lý khi người dùng nhập liệu
if prompt := st.chat_input("Nhập tin nhắn..."):
    # Hiển thị tin nhắn người dùng
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # Logic xử lý (Tương tự code logic ở câu trả lời trước)
    response = ""
    data = get_data_from_sheet() # Lấy data mới nhất
    
    if st.session_state.step == "CHECK_ID":
        # Tìm mã HS trong data
        user = next((item for item in data if str(item["MaHS"]) == prompt.upper()), None)
        if user:
            st.session_state.temp_user = user
            st.session_state.step = "CHECK_DOB"
            response = f"Chào {user['TenHS']}. Vui lòng nhập Ngày sinh (dd/mm/yyyy) để xác thực."
        else:
            response = "Không tìm thấy Mã HS. Vui lòng thử lại."
            
    elif st.session_state.step == "CHECK_DOB":
        if prompt == str(st.session_state.temp_user["NgaySinh"]):
            st.session_state.step = "CHAT"
            st.session_state.current_user = st.session_state.temp_user
            response = "✅ Xác thực thành công! Em có thể hỏi điểm hoặc xem bài làm."
        else:
            response = "Ngày sinh không khớp."

    elif st.session_state.step == "CHAT":
        # Gọi Gemini hoặc xử lý logic đơn giản
        if "bài làm" in prompt.lower():
             link_anh = st.session_state.current_user.get("LinkAnhBaiLam")
             response = f"Đây là bài làm của em: {link_anh}"
             # Streamlit có thể hiển thị ảnh trực tiếp nếu link public hoặc xử lý tải về
        else:
             # Gửi prompt + điểm số cho Gemini xử lý
             response = "(Gemini): Điểm toán của em là " + str(st.session_state.current_user['DiemToan'])

    # Trả lời bot
    st.session_state.messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.write(response)