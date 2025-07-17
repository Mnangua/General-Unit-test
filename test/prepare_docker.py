import subprocess  
import pandas as pd
  
def image_exists(image: str) -> bool:  
    r = subprocess.run(  
        ["docker", "images", "-q", image],  
        stdout=subprocess.PIPE,  
        stderr=subprocess.DEVNULL  
    )  
    return bool(r.stdout.strip())  
  
def container_is_running(name: str) -> bool:  
    r = subprocess.run(  
        ["docker", "ps", "-q", "-f", f"name=^{name}$"],  
        stdout=subprocess.PIPE  
    )  
    return bool(r.stdout.strip())  
  
def container_exists(name: str) -> bool:   
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

    if keep_alive_cmd is None:  
        keep_alive_cmd = ["tail", "-f", "/dev/null"]  

    if image_exists(image):  
        print(f"[INFO] {image} exist, skip pull")  
    else:  
        print(f"[INFO] pull image {image} …")  
        subprocess.run(["docker", "pull", image], check=True)  
   
    if container_is_running(container_name):  
        cid = subprocess.run(  
            ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],  
            stdout=subprocess.PIPE  
        ).stdout.decode().strip()  
        print(f"[INFO] container {container_name} running, ID={cid}")  
        return cid  

    if container_exists(container_name):  
        print(f"[INFO] container {container_name} exist but not running, starting…")  
        subprocess.run(["docker", "start", container_name], check=True)  
        cid = subprocess.run(  
            ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],  
            stdout=subprocess.PIPE  
        ).stdout.decode().strip()  
        print(f"[INFO] complete start, ID={cid}")  
        return cid  

    print(f"[INFO] create and start new container {container_name} …")  
    cmd = ["docker", "run", "-d", "--name", container_name, image] + keep_alive_cmd  
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE)  
    cid = result.stdout.decode().strip()  
    print(f"[SUCCESS] container start successfully, ID={cid}")  
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