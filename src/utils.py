import os
import shlex
import subprocess

TIMEOUT = 1000


class DockerCommandRunner:  
    def __init__(self, container_name: str = None, docker_image: str = None, testbed_path: str = "/testbed"):  
        self.container_name = container_name  
        self.docker_image = docker_image  
        self.testbed_path = testbed_path  
        self._env_activated = False  
    
    def _run_raw_command(self, command):  
        if self.container_name:  
            docker_cmd = f"docker exec {self.container_name} bash -c \"{command}\""  
        else:  
            docker_cmd = f"docker run --rm {self.docker_image} bash -c \"{command}\""  
        try:  
            result = subprocess.run(docker_cmd, shell=True, capture_output=True, text=True, timeout=300)  
            return {  
                "stdout": result.stdout,  
                "stderr": result.stderr,  
                "returncode": result.returncode  
            }  
        except subprocess.TimeoutExpired:  
            return {"stdout": "", "stderr": "Command timed out", "returncode": -1}  
        except Exception as e:  
            return {"stdout": "", "stderr": str(e), "returncode": -1}  
  
    def run_command(self, command, work_dir = None):  
        env_prefix = ". /opt/activate_python.sh && "  
        if work_dir:  
            full = f"{env_prefix}cd {self.testbed_path}/{work_dir.strip('/')} && {command}"  
        else:  
            full = f"{env_prefix}cd {self.testbed_path} && {command}"  
        if self.container_name:  
            docker_cmd = f"docker exec {self.container_name} bash -c \"{full}\""  
        else:  
            docker_cmd = f"docker run --rm {self.docker_image} bash -c \"{full}\""  
        result = subprocess.run(docker_cmd, shell=True, capture_output=True, text=True, timeout=300)  
        return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}  
  
    def copy_file_from_container(self, container_path, local_path):  
        if not self.container_name:  
            print("Warning: Cannot copy files without container name")  
            return False  
        os.makedirs(os.path.dirname(local_path), exist_ok=True)  
        cmd = f"docker cp {self.container_name}:{container_path} {local_path}"  
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)  
        return result.returncode == 0 and os.path.exists(local_path)  
    
    def copy_file_to_container(self, local_path, container_path):  
        if not self.container_name:  
            print("Warning: Cannot copy files without container name")  
            return False  
        cmd = f"docker cp {local_path} {self.container_name}:{container_path}"  
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)  
        return result.returncode == 0 and os.path.exists(container_path)
  
    def list_testbed_contents(self):  
        res = self.run_command("ls -la")  
        return res["stdout"].splitlines() if res["returncode"] == 0 else [] 
    
    def write_file_to_container(self, content: str, container_path: str) -> bool:  
        if not self.container_name:  
            print("Warning: Cannot write files without container name")  
            return False  
        
        container_abs = os.path.join(self.testbed_path, container_path.lstrip('/'))  
        print(f"Writing to container path: {container_abs}")
        parent = os.path.dirname(container_abs)  
        if parent:  
            self.run_command(f'mkdir -p "{parent}"')  
  
        cmd = (  
            f"cat > \"{container_abs}\" << 'EOFILE'\n"  
            f"{content}\n"  
            "EOFILE"  
        )  
        res = self.run_command(cmd)  
        if res["returncode"] != 0:  
            print(f"✗ 写入容器失败: {res['stderr']}")  
            return False  
        return True


def run_custom_command(work_dir: str, command: str) -> dict:
    """
    Run any custom Linux command within the Local env.
    Returns:
        dict: A dictionary with the testing result, including status, stdout, stderr.
    """
    shell = os.name == "nt"
    try:
        output = subprocess.run(shlex.split(command), shell=shell, cwd=work_dir, capture_output=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        result = {"success": False, "stdout": "n/a", "stderr": f"Timeout"}
        return result

    stdout = output.stdout.decode("utf-8")
    stderr = output.stderr.decode("utf-8")
    result = {"stdout": stdout, "stderr": stderr}
    return result


def run_command_real_time(work_dir: str, command: str, log_file: str) -> int:
    _process = subprocess.Popen(
        shlex.split(command),
        shell=False,
        # We pipe the output to an internal pipe
        stdout=subprocess.PIPE,
        # Make sure that if this Python program is killed, this gets killed too
        preexec_fn=os.setsid,
        cwd=work_dir,
    )

    with open(log_file, "a") as fw:
        # Poll for output, note: readline() blocks efficiently until there is output with a newline
        while True:
            output = _process.stdout.readline()
            fw.write(output.decode("utf-8"))
            # Polling returns None when the program is still running, return_code otherwise
            return_code = _process.poll()
            if return_code is not None:
                # Program ended, get exit/return code
                return return_code
