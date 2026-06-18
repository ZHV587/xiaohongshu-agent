import paramiko
import sys

IP = "124.221.173.80"
USERNAME = "ubuntu"
PASSWORD = "1234567890Zh."
PORT = 22

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(IP, port=PORT, username=USERNAME, password=PASSWORD, timeout=15)
        print("Connected.")
        
        # Get PM2 logs / status
        commands = [
            "pm2 status",
            "tail -n 50 /home/ubuntu/.pm2/logs/xhs-backend-out.log",
            "tail -n 50 /home/ubuntu/.pm2/logs/xhs-backend-error.log"
        ]
        
        for cmd in commands:
            print(f"\n=== Running: {cmd} ===")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode('utf-8', errors='ignore')
            err = stderr.read().decode('utf-8', errors='ignore')
            print("STDOUT:")
            print(out)
            if err:
                print("STDERR:")
                print(err)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
