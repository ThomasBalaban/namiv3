import subprocess
import os
import signal

PORTS = [8001, 8002, 8003]

def check_ports():
    print(f"🔍 Checking ports: {PORTS}...\n")
    for port in PORTS:
        try:
            # Run lsof to see what is on the port
            result = subprocess.check_output(["lsof", "-i", f":{port}", "-t"], text=True).strip()
            if result:
                pids = result.split('\n')
                print(f"⚠️  Port {port} is IN USE by PID(s): {', '.join(pids)}")
                
                # Optional: Uncomment to auto-kill
                # for pid in pids:
                #     print(f"    💀 Killing PID {pid}...")
                #     os.kill(int(pid), signal.SIGKILL)
            else:
                print(f"✅ Port {port} is free.")
        except subprocess.CalledProcessError:
            print(f"✅ Port {port} is free.")
        except Exception as e:
            print(f"❌ Error checking port {port}: {e}")

if __name__ == "__main__":
    check_ports()