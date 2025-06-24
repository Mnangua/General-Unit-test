import subprocess  
import pandas as pd
  
def image_exists(image: str) -> bool:  
    # 返回本地是否有这个 image  
    r = subprocess.run(  
        ["docker", "images", "-q", image],  
        stdout=subprocess.PIPE,  
        stderr=subprocess.DEVNULL  
    )  
    return bool(r.stdout.strip())  
  
def container_is_running(name: str) -> bool:  
    # 返回是否有正在运行的同名容器  
    r = subprocess.run(  
        ["docker", "ps", "-q", "-f", f"name=^{name}$"],  
        stdout=subprocess.PIPE  
    )  
    return bool(r.stdout.strip())  
  
def container_exists(name: str) -> bool:  
    # 返回是否有（任意状态）同名容器  
    r = subprocess.run(  
        ["docker", "ps", "-aq", "-f", f"name=^{name}$"],  
        stdout=subprocess.PIPE  
    )  
    return bool(r.stdout.strip())  
  
def pull_and_run_background(  
    image: str,  
    container_name: str,  
    keep_alive_cmd=None  
) -> str:  
    """  
    1) 本地无 image 则 pull  
    2) 容器名已在 running 则返回其 ID  
    3) 容器名已存在但未 running 则 start 并返回 ID  
    4) 否则 run -d 新建保活容器 tail -f /dev/null  
    返回最终的 container_id  
    """  
    if keep_alive_cmd is None:  
        keep_alive_cmd = ["tail", "-f", "/dev/null"]  
  
    # # 1) 拉取镜像（如果本地不存在）  
    # if image_exists(image):  
    #     print(f"[INFO] 镜像 {image} 已存在，跳过 pull")  
    # else:  
    #     print(f"[INFO] 拉取镜像 {image} …")  
    #     subprocess.run(["docker", "pull", image], check=True)  
  
    # 2) 容器是否已在运行？  
    if container_is_running(container_name):  
        cid = subprocess.run(  
            ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],  
            stdout=subprocess.PIPE  
        ).stdout.decode().strip()  
        print(f"[INFO] 容器 {container_name} 已在运行，ID={cid}")  
        return cid  
  
    # 3) 容器存在但未运行？  
    if container_exists(container_name):  
        print(f"[INFO] 容器 {container_name} 已存在但未运行，正在启动…")  
        subprocess.run(["docker", "start", container_name], check=True)  
        cid = subprocess.run(  
            ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],  
            stdout=subprocess.PIPE  
        ).stdout.decode().strip()  
        print(f"[INFO] 启动完成，ID={cid}")  
        return cid  
  
    # 4) 新建并后台运行容器  
    print(f"[INFO] 创建并启动新容器 {container_name} …")  
    cmd = ["docker", "run", "-d", "--name", container_name, image] + keep_alive_cmd  
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE)  
    cid = result.stdout.decode().strip()  
    print(f"[SUCCESS] 容器启动成功，ID={cid}")  
    return cid
  
  
if __name__ == "__main__": 
    csv_file = "/home/mengnanqi/General-Unit-Test/exp_data/metadata_fix_part.csv" 
    df = pd.read_csv(csv_file)
    for index, row in df.iterrows():
        image = row['image_tag']
        #image = "codeexecservice.azurecr.io/" + image
        container_name = row['instance_id']
        print(f"Processing {container_name} with image {image} ...")
        pull_and_run_background(image, container_name)  