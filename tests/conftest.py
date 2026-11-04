import os
import sys

# Tests never write turn logs, and import modules from the project root.
os.environ["EV_AGENT_LOG_PATH"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
