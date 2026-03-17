import os
import subprocess
import time

def check_server():
    env = os.environ.copy()
    env["PYTHONPATH"] = "H:\\AI\\Django"
    
    print("Attempting to start server and capture output...")
    process = subprocess.Popen(
        ["H:\\AI\\Django\\venv3.12\\Scripts\\python.exe", "manage.py", "runserver", "8001", "--noreload"],
        cwd="H:\\AI\\Django",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    try:
        # 讀取前 10 行輸出
        for _ in range(20):
            line = process.stdout.readline()
            if line:
                print(f"SERVER: {line.strip()}")
            if "Quit the server" in line:
                print("Server seems to be running.")
                break
            time.sleep(0.5)
            if process.poll() is not None:
                print(f"Server exited early with code {process.returncode}")
                break
    finally:
        process.terminate()

if __name__ == "__main__":
    check_server()
