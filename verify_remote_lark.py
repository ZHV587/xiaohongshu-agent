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
        
        commands = [
            "/home/ubuntu/xiaohongshu-agent/.venv/bin/python -c \"from tools.feishu_bitable import read_xhs_data; import pprint; res = read_xhs_data.func(); print('Error:', res.get('error')); print('Rows Count:', len(res.get('rows', []))); pprint.pprint(res.get('rows', [])[:3])\""
        ]
        
        for cmd in commands:
            print(f"\n=== Running: {cmd} ===")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode('utf-8', errors='ignore')
            err = stderr.read().decode('utf-8', errors='ignore')
            print("STDOUT (truncated):")
            print(out[:400])
            if err:
                print("STDERR:")
                print(err[:400])
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
