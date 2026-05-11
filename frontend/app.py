import streamlit as st
import uuid
import os
import sys
from pathlib import Path

# Ensure src is in python path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import AgentState
from langgraph.types import Command

st.set_page_config(page_title="LangGraph Agent UI", page_icon="🤖", layout="wide")

# Enable True HITL for this process
os.environ["LANGGRAPH_INTERRUPT"] = "true"

@st.cache_resource
def get_graph():
    # We use Postgres as our persistent storage via Docker
    db_url = "postgresql://postgres:postgres@localhost:5432/langgraph_lab"
    checkpointer = build_checkpointer("postgres", db_url)
    return build_graph(checkpointer=checkpointer)

try:
    graph = get_graph()
except Exception as e:
    st.error(f"Failed to load graph or connect to DB. Ensure Docker is running. Error: {e}")
    st.stop()

# --- Session Initialization ---
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.scenario_id = "UI_Session"
    st.session_state.messages = []

config = {"configurable": {"thread_id": st.session_state.thread_id}}

st.title("🤖 Support Agent with HITL")
st.markdown(f"**Thread ID:** `{st.session_state.thread_id}`")

# --- Render Chat History ---
st.subheader("Chat Interface")

# We sync Streamlit state messages with the actual Graph state if we want to, 
# but for simplicity we keep our own basic log in st.session_state.messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Determine Current State & Interrupts ---
current_state = graph.get_state(config)
is_interrupted = len(current_state.next) > 0 and current_state.next[0] == "approval"

if is_interrupted:
    st.warning("⚠️ **Human-in-the-loop Approval Required**")
    
    # Extract interrupt data
    task = next((t for t in current_state.tasks if t.name == "approval"), None)
    
    if task and task.interrupts:
        interrupt_data = task.interrupts[0].value
        
        st.info("The agent wants to perform a high-risk action. Please review:")
        st.json(interrupt_data)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Approve Action", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": "*User approved the action.*"})
                # Resume execution with Command
                for chunk in graph.stream(Command(resume={"approved": True, "comment": "Approved by Human"}), config=config):
                    pass
                st.rerun()
                
        with col2:
            if st.button("❌ Reject Action", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": "*User rejected the action.*"})
                # Resume execution with Command
                for chunk in graph.stream(Command(resume={"approved": False, "comment": "Rejected by Human"}), config=config):
                    pass
                st.rerun()

# --- User Input ---
elif prompt := st.chat_input("Enter your support query (e.g., 'Delete my account')..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    with st.spinner("Agent is thinking..."):
        initial_input = {
            "query": prompt,
            "scenario_id": st.session_state.scenario_id,
            "thread_id": st.session_state.thread_id,
            "max_attempts": 3
        }
        
        for chunk in graph.stream(initial_input, config=config):
            pass
            
        # Re-fetch state to get output
        current_state = graph.get_state(config)
        state_values = current_state.values
        
        # Check if it was interrupted right after our input
        is_interrupted_now = len(current_state.next) > 0 and current_state.next[0] == "approval"
        
        if not is_interrupted_now:
            # If not interrupted, we should have a final answer or pending question
            if "final_answer" in state_values and state_values["final_answer"]:
                ans = state_values["final_answer"]
                st.session_state.messages.append({"role": "assistant", "content": ans})
            elif "pending_question" in state_values and state_values["pending_question"]:
                ans = state_values["pending_question"]
                st.session_state.messages.append({"role": "assistant", "content": ans})
        
    st.rerun()
