#!/usr/bin/env python3
"""
Docker容器复制脚本
从CSV文件读取instance_id，将现有Docker容器复制为新容器（添加-postprocess-v1后缀）
"""

import csv
import subprocess
import sys
import json
from pathlib import Path


def get_container_info(container_name):
    """获取容器信息"""
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
    """检查Docker容器是否存在"""
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
    """检查容器是否正在运行"""
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
    """将容器提交为镜像"""
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
    """基于镜像创建新容器，保持原容器的配置"""
    try:
        # 获取原容器的配置信息
        config = original_container_info.get('Config', {})
        host_config = original_container_info.get('HostConfig', {})
        
        # 构建docker run命令
        cmd = ['docker', 'create', '--name', container_name]
        
        # 添加环境变量
        if config.get('Env'):
            for env in config['Env']:
                cmd.extend(['-e', env])
        
        # 添加端口映射
        if host_config.get('PortBindings'):
            for container_port, host_bindings in host_config['PortBindings'].items():
                if host_bindings:
                    for binding in host_bindings:
                        host_port = binding.get('HostPort', '')
                        if host_port:
                            cmd.extend(['-p', f"{host_port}:{container_port}"])
        
        # 添加卷挂载
        if host_config.get('Binds'):
            for bind in host_config['Binds']:
                cmd.extend(['-v', bind])
        
        # 添加工作目录
        if config.get('WorkingDir'):
            cmd.extend(['-w', config['WorkingDir']])
        
        # 添加镜像名
        cmd.append(image_name)
        
        # 添加原始命令
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
    """复制容器的完整流程"""
    print(f"  步骤1: 检查源容器 {source_container} 是否存在...")
    if not check_container_exists(source_container):
        return False, "源容器不存在"
    
    print(f"  步骤2: 获取源容器信息...")
    container_info = get_container_info(source_container)
    if not container_info:
        return False, "无法获取容器信息"
    
    # 临时镜像名
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
    """列出所有Docker容器"""
    try:
        result = subprocess.run(
            ['docker', 'ps', '-a', '--format', 'table {{.Names}}\t{{.Status}}\t{{.Image}}'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"错误: {e.stderr}"


def list_containers_from_csv(csv_file):
    """列出CSV文件中对应的容器状态"""
    if not csv_file.exists():
        print(f"错误: CSV文件不存在: {csv_file}")
        return
    
    print("CSV文件中的容器状态:")
    print("=" * 80)
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            instance_id = row['instance_id']
            
            # 检查容器是否存在
            exists = check_container_exists(instance_id)
            running = check_container_running(instance_id) if exists else False
            
            status = "存在且运行中" if running else ("存在但已停止" if exists else "不存在")
            status_icon = "🟢" if running else ("🟡" if exists else "🔴")
            
            print(f"{status_icon} {instance_id}: {status}")


def main():
    # CSV文件路径
    csv_file = Path('/home/mengnanqi/General-Unit-Test/results/python/base_msbench_results.csv')
    
    if not csv_file.exists():
        print(f"错误: CSV文件不存在: {csv_file}")
        sys.exit(1)
    
    print("开始读取CSV文件并复制Docker容器...")
    print("=" * 80)
    
    success_count = 0
    error_count = 0
    not_found_count = 0
    
    # 读取CSV文件
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            instance_id = row['instance_id']
            
            # 创建新的容器名（添加后缀）
            source_container = instance_id
            target_container = f"{instance_id}-postprocess-v1"
            
            print(f"\n处理 {instance_id}:")
            print(f"  源容器: {source_container}")
            print(f"  目标容器: {target_container}")
            
            # 检查源容器是否存在
            if not check_container_exists(source_container):
                print(f"  ❌ 源容器不存在，跳过")
                not_found_count += 1
                continue
            
            # 检查目标容器是否已存在
            if check_container_exists(target_container):
                print(f"  ⚠️  目标容器已存在，跳过")
                continue
            
            # 复制容器
            success, message = copy_container(source_container, target_container)
            
            if success:
                print(f"  ✅ {message}")
                success_count += 1
            else:
                print(f"  ❌ 复制失败: {message}")
                error_count += 1
    
    # 输出统计信息
    print("\n" + "=" * 80)
    print("复制完成统计:")
    print(f"  成功复制: {success_count} 个容器")
    print(f"  复制失败: {error_count} 个容器")
    print(f"  源容器不存在: {not_found_count} 个容器")
    print(f"  总计处理: {success_count + error_count + not_found_count} 个容器")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        # 列出所有容器
        print("所有Docker容器:")
        print("=" * 80)
        print(list_all_containers())
        
        # 列出CSV文件中容器的状态
        csv_file = Path('/home/mengnanqi/General-Unit-Test/results/python/base_msbench_results.csv')
        list_containers_from_csv(csv_file)
    else:
        # 执行复制操作
        main()
