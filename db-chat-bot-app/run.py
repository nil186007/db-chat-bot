"""
Entry point for running the Database ChatBot application.
"""
import subprocess
import sys
import os
from pathlib import Path

if __name__ == "__main__":
    # Get the project root directory
    project_root = Path(__file__).parent
    src_dir = project_root / "src"
    
    # Add src to Python path
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    
    # Set PYTHONPATH environment variable
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_dir) + (os.pathsep + env.get("PYTHONPATH", ""))
    
    # Run the Streamlit app
    app_path = src_dir / "db_chatbot" / "frontend" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)], env=env)

