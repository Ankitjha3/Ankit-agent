import os
import sys
import subprocess

def check_install_dependencies():
    print("Checking python dependencies...")
    try:
        import fastapi
        import uvicorn
        import sqlalchemy
        import pydantic
        import dotenv
        import langchain
        import langchain_openai
        print("All dependencies are already installed!")
    except ImportError:
        print("Some dependencies are missing. Installing required packages from backend/requirements.txt...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", "backend/requirements.txt"], check=True)
            print("Packages installed successfully!")
        except Exception as e:
            print(f"Error installing dependencies: {e}")
            print("Please make sure pip is installed and run 'pip install -r backend/requirements.txt' manually.")
            sys.exit(1)

def setup_env():
    if not os.path.exists(".env"):
        print("No .env file found. Creating one from .env.example...")
        try:
            with open(".env.example", "r") as f_in:
                content = f_in.read()
            with open(".env", "w") as f_out:
                f_out.write(content)
            print("Created .env file. Please edit it and fill in your OPENAI_API_KEY!")
        except Exception as e:
            print(f"Could not create .env file: {e}")

def run_server():
    print("\n--------------------------------------------------")
    print("Starting AI Task Agent Server...")
    print("Once started, open your browser at: http://localhost:8000")
    print("--------------------------------------------------\n")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    port = int(os.getenv("PORT", 8000))
    
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, reload=True)

if __name__ == "__main__":
    # Ensure current working directory is the script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    check_install_dependencies()
    setup_env()
    run_server()
