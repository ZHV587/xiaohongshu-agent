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
        
        # Install lark-cli globally
        cmd = "sudo npm install -g @larksuite/cli"
        print(f"Running: {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        # Block until completion and print logs
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode('utf-8', errors='ignore')
        err = stderr.read().decode('utf-8', errors='ignore')
        print(f"Exit status: {exit_status}")
        print("STDOUT:")
        print(out)
        if err:
            print("STDERR:")
            print(err)
            
        # Verify installation
        cmd_ver = "lark-cli --version"
        stdin, stdout, stderr = ssh.exec_command(cmd_ver)
        print("lark-cli version:")
        print(stdout.read().decode('utf-8', errors='ignore'))
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
