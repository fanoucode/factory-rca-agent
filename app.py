import streamlit as st
import pandas as pd
import altair as alt
import time
from fpdf import FPDF
from datetime import datetime
from google import genai
from PIL import Image

# --- CONFIGURATION ---
st.set_page_config(page_title="Factory RCA Agent", layout="wide")

# --- API KEY SETUP (Cloud & Local) ---
# This logic allows the app to work both on your laptop and on the cloud.
if "GOOG_API_KEY" in st.secrets:
    # 1. If running on Streamlit Cloud, get key from Secrets
    GOOG_API_KEY = st.secrets["GOOG_API_KEY"]
else:
    # 2. If running locally, use this fallback key
    # REPLACE THE TEXT BELOW WITH YOUR ACTUAL API KEY FOR LOCAL TESTING
    GOOG_API_KEY = "PASTE_YOUR_KEY_HERE" 

# --- SETUP GEMINI CLIENT ---
try:
    client = genai.Client(api_key=GOOG_API_KEY)
except Exception as e:
    st.error(f"⚠️ API Client Setup Failed: {e}")

# --- 1. DIGITAL TWIN (Context) ---
FACTORY_PROFILE = {
    "Line_4": {
        "Product": "Strawberry Yogurt (pH 4.4)",
        "Flow": "Pasto -> Buffer Tank -> Fruit Doser -> Filler",
        "Last_CIP": "Yesterday 22:00",
        "Risk_Category": "High Acid (Yeast/Mold Risk)",
        "Threshold": 50
    },
    "Line_2": {
        "Product": "UHT Vanilla Dessert (pH 6.5)",
        "Flow": "Sterilizer -> Aseptic Tank -> Filler",
        "Last_CIP": "Today 04:00",
        "Risk_Category": "Low Acid (Bacteria Risk)",
        "Threshold": 1
    }
}

# --- HELPER: CONVERSATIONAL AI CALL ---
def ask_the_team_conversational(context, history):
    """
    Sends the ENTIRE chat history to Gemini so it remembers the image and previous context.
    """
    
    # 1. The "System Prompt" (Hidden Context)
    system_instruction = f"""
    You are the AI Operating System for a food factory.
    
    CONTEXT:
    - Product: {context['Product']}
    - Process Flow: {context['Flow']}
    - Risk Category: {context['Risk_Category']}
    
    ROLE:
    You simulate a root cause analysis meeting between a MICROBIOLOGIST and a PROCESS ENGINEER.
    
    INSTRUCTIONS:
    - If this is the start of a generic incident, provide two distinct hypotheses (MICRO:| and ENGINEER:|).
    - If the user asks a specific follow-up question (e.g., "What bug is that?"), answer directly as the relevant expert.
    - Always stay in character. Be technical.
    """
    
    # 2. Reconstruct the Conversation for the API
    api_contents = []
    
    # Add System Instruction first
    api_contents.append(system_instruction)
    
    # Loop through history
    for msg in history:
        parts = []
        
        # Add Text
        if msg["content"]:
            parts.append(msg["content"])
            
        # Add Image if present
        if "image" in msg and msg["image"]:
            parts.append(msg["image"])
            
        # Add to API list
        if parts:
            api_contents.append(parts)
            
    try:
        # 3. Call Gemini with full history
        # Using 'gemini-flash-latest' for best free-tier compatibility
        response = client.models.generate_content(
            model='gemini-flash-latest', 
            contents=api_contents
        )
        return response.text
        
    except Exception as e:
        return f"⚠️ Connection Error: {e}"

# --- PDF GENERATION ---
def create_pdf(line, issue, root_cause, action):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Microbiological RCA Report", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.cell(200, 10, txt=f"Line: {line}", ln=True)
    pdf.cell(200, 10, txt=f"Issue: {issue}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Final Determination", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, txt=f"Root Cause: {root_cause}")
    pdf.ln(5)
    pdf.multi_cell(0, 10, txt=f"Action: {action}")
    file_name = f"RCA_Report_{int(time.time())}.pdf"
    pdf.output(file_name)
    return file_name

# --- UI SETUP ---
st.title("🦠 RCA Agent (Cloud Edition)")
st.markdown("---")
st.sidebar.header("🏭 Factory Context")
selected_line = st.sidebar.selectbox("Select Production Line", ["Line_4", "Line_2"])
context = FACTORY_PROFILE[selected_line]
st.sidebar.json(context)

# --- SESSION STATE ---
if "messages" not in st.session_state: st.session_state.messages = []
if "investigation_active" not in st.session_state: st.session_state.investigation_active = False
if "rca_complete" not in st.session_state: st.session_state.rca_complete = False

# --- CHAT HISTORY ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "image" in message and message["image"]:
            st.image(message["image"], width=200)

# --- INPUT AREA ---
col1, col2 = st.columns([4, 1])
with col1:
    prompt = st.chat_input("Ask the team (e.g., 'What kind of bug is this?')...")
with col2:
    uploaded_img = st.file_uploader("📷 Add Photo", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

# --- TRIGGER LOGIC ---
if prompt:
    st.session_state.investigation_active = True
    
    # Handle Image Upload
    pil_image = None
    if uploaded_img:
        pil_image = Image.open(uploaded_img)
        st.session_state.messages.append({"role": "user", "content": prompt, "image": pil_image})
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})

    # Display User Message
    with st.chat_message("user"):
        st.markdown(prompt)
        if pil_image: st.image(pil_image, width=300)

    # Generate Response
    with st.chat_message("assistant"):
        with st.spinner("Agents are discussing..."):
            ai_response = ask_the_team_conversational(context, st.session_state.messages)
            st.markdown(ai_response)
            st.session_state.messages.append({"role": "assistant", "content": ai_response})

# --- INVESTIGATION PHASE ---
if st.session_state.investigation_active:
    st.markdown("---")
    st.subheader("📂 Evidence Upload")
    uploaded_file = st.file_uploader("Upload Lab Data (CSV)", type="csv")
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        chart = alt.Chart(df).mark_line(point=True).encode(x='Date', y='Count').properties(width=600).interactive()
        st.altair_chart(chart)
        
        avg_count = df['Count'].mean()
        limit = context['Threshold']
        
        if selected_line == "Line_2":
            if avg_count > limit:
                st.error(f"🚨 **CRITICAL:** Counts > {limit} in UHT!")
                if st.button("Generate Critical Report"):
                     pdf_file = create_pdf(selected_line, "UHT Breach", "Sterility Failure", "STOP PRODUCTION")
                     with open(pdf_file, "rb") as f: st.download_button("Download PDF", f, file_name=pdf_file)
            else: st.success("✅ Data Clean.")
        else:
            if avg_count > limit: st.error("❌ Systemic Hygiene Failure.")
            else:
                 st.warning("⚠️ Sporadic Spikes detected.")
                 st.markdown("---")
                 st.markdown("**Question:** Inspect dosing valve O-ring.")
                 col1, col2 = st.columns(2)
                 if col1.button("O-ring OK"): st.info("Check Piston Head.")
                 if col2.button("O-ring Cracked"):
                     st.session_state.rca_complete = True
                 
                 if st.session_state.rca_complete:
                     st.success("✅ ROOT CAUSE CONFIRMED.")
                     last_issue = st.session_state.messages[-2]['content'] if len(st.session_state.messages) > 1 else "Visual Defect"
                     pdf_file = create_pdf(selected_line, last_issue, "Mechanical Failure", "Replace Seal")
                     with open(pdf_file, "rb") as f: st.download_button("Download Report", f, file_name="RCA_Final.pdf")