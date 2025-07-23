import streamlit as st
import requests
import json
from datetime import datetime
import uuid

# Configure Streamlit
st.set_page_config(
    page_title="Academic Research Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# FastAPI backend URL
API_BASE_URL = "http://localhost:8000"

# Initialize session state
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())[:8]

if "messages" not in st.session_state:
    st.session_state.messages = []

if "search_history" not in st.session_state:
    st.session_state.search_history = []

def call_api(endpoint, method="GET", data=None):
    """Make API calls to FastAPI backend"""
    try:
        url = f"{API_BASE_URL}/{endpoint}"
        if method == "POST":
            response = requests.post(url, json=data)
        else:
            response = requests.get(url)
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot connect to backend. Make sure FastAPI server is running on port 8000")
        return None
    except Exception as e:
        st.error(f"API Error: {str(e)}")
        return None

def display_message(message, is_user=True):
    """Display chat message"""
    if is_user:
        st.markdown(f"**You:** {message}")
    else:
        st.markdown(f"**Assistant:** {message}")

def main():
    st.title("📚 Academic Research Assistant")
    st.markdown("*Find and summarize academic papers with AI-powered search*")
    
    # Sidebar
    with st.sidebar:
        st.header("📊 Your Profile")
        st.write(f"User ID: `{st.session_state.user_id}`")
        
        # Search History
        st.subheader("🔍 Recent Searches")
        if st.button("Refresh History"):
            history_data = call_api(f"search-history/{st.session_state.user_id}")
            if history_data:
                st.session_state.search_history = history_data.get("history", [])
        
        if st.session_state.search_history:
            for item in st.session_state.search_history[:5]:
                st.text(f"• {item['query']}")
        else:
            st.text("No searches yet")
        
        # User Interests
        st.subheader("💡 Your Interests")
        interests_data = call_api(f"user-interests/{st.session_state.user_id}")
        if interests_data and interests_data.get("interests"):
            for interest in interests_data["interests"][:5]:
                st.text(f"• {interest['topic'].title()} ({interest['score']})")
        else:
            st.text("No interests tracked yet")
        
        # Quick Actions
        st.subheader("⚡ Quick Actions")
        if st.button("Clear Chat"):
            st.session_state.messages = []
            st.rerun()
        
        if st.button("Example Queries"):
            st.session_state.messages = [
                {"role": "assistant", "content": "Try these example queries:"},
                {"role": "assistant", "content": "1. 'Find me 3 papers about federated learning in 2022'"},
                {"role": "assistant", "content": "2. 'Can you summarize the first one?'"},
                {"role": "assistant", "content": "3. 'Show me my previous searches on AI topics'"}
            ]
    
    # Main chat area
    st.subheader("💬 Research Chat")
    
    # Display chat messages
    for message in st.session_state.messages:
        display_message(message["content"], is_user=message["role"] == "user")
    
    # Chat input
    user_input = st.chat_input("Ask about research papers...")
    
    if user_input:
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": user_input})
        display_message(user_input, is_user=True)
        
        # Call backend API
        response = call_api(
            "chat",
            method="POST",
            data={
                "user_id": st.session_state.user_id,
                "message": user_input
            }
        )
        
        if response:
            # Display assistant response
            assistant_response = response.get("response", "I didn't get a response.")
            st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            display_message(assistant_response, is_user=False)
            
            # Handle special responses (papers, summaries)
            if "papers" in response and isinstance(response["papers"], list):
                for paper in response["papers"]:
                    paper_text = f"📄 **{paper['title']}**\nAuthors: {', '.join(paper['authors'])}\nYear: {paper['year']}" # Added join for authors
                    st.session_state.messages.append({"role": "assistant", "content": paper_text})
                    display_message(paper_text, is_user=False)
            
            if "summary" in response:
                st.session_state.messages.append({"role": "assistant", "content": f"📝 Summary:\n{response['summary']}"})
                display_message(f"📝 Summary:\n{response['summary']}", is_user=False)

if __name__ == "__main__":
    main()