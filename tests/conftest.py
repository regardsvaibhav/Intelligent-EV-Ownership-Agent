import os
import sys

# Tests never write turn logs, and import modules from the project root.
os.environ["EV_AGENT_LOG_PATH"] = ""
# Tests never call a real LLM API, even if LLM_API_KEY / GEMINI_API_KEY is set on this machine.
os.environ["LLM_FALLBACK"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
