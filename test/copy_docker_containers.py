#!/usr/bin/env python3
import csv
import subprocess
import sys
import json
from pathlib import Path


def get_container_info(container_name):
    try:
        result = subprocess.run(
            ['docker', 'inspect', container_name],
            capture_output=True,
            text=True,
            check=True
        )
        container_info = json.loads(result.stdout)[0]
        return container_info
    except subprocess.CalledProcessError:
        return None


def check_container_exists(container_name):
    try:
        result = subprocess.run(
            ['docker', 'inspect', container_name],
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def check_container_running(container_name):
    try:
        result = subprocess.run(
            ['docker', 'inspect', '-f', '{{.State.Running}}', container_name],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip() == 'true'
    except subprocess.CalledProcessError:
        return False


def commit_container_to_image(container_name, image_name):
    try:
        result = subprocess.run(
            ['docker', 'commit', container_name, image_name],
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr


def create_container_from_image(image_name, container_name, original_container_info):
    try:
        config = original_container_info.get('Config', {})
        host_config = original_container_info.get('HostConfig', {})

        cmd = ['docker', 'create', '--name', container_name]

        if config.get('Env'):
            for env in config['Env']:
                cmd.extend(['-e', env])

        if host_config.get('PortBindings'):
            for container_port, host_bindings in host_config['PortBindings'].items():
                if host_bindings:
                    for binding in host_bindings:
                        host_port = binding.get('HostPort', '')
                        if host_port:
                            cmd.extend(['-p', f"{host_port}:{container_port}"])

        if host_config.get('Binds'):
            for bind in host_config['Binds']:
                cmd.extend(['-v', bind])

        if config.get('WorkingDir'):
            cmd.extend(['-w', config['WorkingDir']])

        cmd.append(image_name)

        if config.get('Cmd'):
            cmd.extend(config['Cmd'])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr


def copy_container(source_container, target_container):
    print(f"  步骤1: 检查源容器 {source_container} 是否存在...")
    if not check_container_exists(source_container):
        return False, "源容器不存在"
    
    print(f"  步骤2: 获取源容器信息...")
    container_info = get_container_info(source_container)
    if not container_info:
        return False, "无法获取容器信息"

    temp_image = f"temp-{target_container}-image"
    
    print(f"  步骤3: 将容器提交为临时镜像 {temp_image}...")
    success, result = commit_container_to_image(source_container, temp_image)
    if not success:
        return False, f"提交容器为镜像失败: {result}"
    
    print(f"  步骤4: 基于临时镜像创建新容器 {target_container}...")
    success, result = create_container_from_image(temp_image, target_container, container_info)
    
    # 清理临时镜像
    print(f"  步骤5: 清理临时镜像...")
    try:
        subprocess.run(['docker', 'rmi', temp_image], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print(f"    警告: 无法删除临时镜像 {temp_image}")
    
    if not success:
        return False, f"创建新容器失败: {result}"
    
    return True, "容器复制成功"


def list_all_containers():
    try:
        result = subprocess.run(
            ['docker', 'ps', '-a', '--format', 'table {{.Names}}\t{{.Status}}\t{{.Image}}'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"error: {e.stderr}"


def list_containers_from_csv(csv_file):
    if not csv_file.exists():
        print(f"error: CSV file not exist, {csv_file}")
        return
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            instance_id = row['instance_id']
            exists = check_container_exists(instance_id)
            running = check_container_running(instance_id) if exists else False
            
            status = "exist and running" if running else ("exist but stop running" if exists else "not exist")
            status_icon = "🟢" if running else ("🟡" if exists else "🔴")
            
            print(f"{status_icon} {instance_id}: {status}")


def main():
    csv_file = Path('/home/mengnanqi/General-Unit-Test/results/python/base_msbench_results.csv')        
    success_count = 0
    error_count = 0
    not_found_count = 0
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            instance_id = row['instance_id']
            source_container = instance_id
            target_container = f"{instance_id}-postprocess-v1"
            
            if not check_container_exists(source_container):
                print(f"  ❌ source container not exist, skipping copy")
                not_found_count += 1
                continue

            if check_container_exists(target_container):
                print(f"  ⚠️  target container exist, skipping copy")
                continue

            success, message = copy_container(source_container, target_container)
            
            if success:
                print(f"  ✅ {message}")
                success_count += 1
            else:
                print(f"  ❌ copy failed: {message}")
                error_count += 1

    print("\n" + "=" * 80)
    print("Copy completion statistics:")
    print(f"  Successfully copied: {success_count} containers")
    print(f"  Failed to copy: {error_count} containers")
    print(f"  Source containers not found: {not_found_count} containers")
    print(f"  Total processed: {success_count + error_count + not_found_count} containers")


if __name__ == "__main__":
    csv_file = Path('/home/mengnanqi/General-Unit-Test/results/python/base_msbench_results.csv')
    list_containers_from_csv(csv_file)

