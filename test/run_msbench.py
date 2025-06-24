import subprocess  
import pandas as pd  
from src.generate.unit_test_generator import CoverageBasedTestGenerator  
from src.postprocess.error_fixer import create_error_fixer
from src.capi_client import CopilotProxyLLMClient  
import argparse  
from tqdm import tqdm  
  
parser = argparse.ArgumentParser(description="Generate tests on msbench")  
parser.add_argument("--temp-dir", default="./docker_output/postprocess_v1_exp_part", help="Temporary directory for test generation")
parser.add_argument("--language", default="python", choices=["python", "java"], help="Programming language")  
parser.add_argument("--model", default="claude-3.5-sonnet", help="LLM model to use")  
parser.add_argument("--use-related-searcher", action="store_true",  
                    help="Use related code searcher for better context")
parser.add_argument("--enable-error-fixing", action="store_true",
                    help="Enable error fixing after test generation")
parser.add_argument("--enable-generate", action="store_true",
                    help="Enable test generation")
parser.add_argument("--max-fix-iterations", type=int, default=10,
                    help="Maximum error fix iterations")
args = parser.parse_args()  
  
csv_file = "/home/mengnanqi/General-Unit-Test/exp_data/metadata_fix.csv"  
tgt_file = "/home/mengnanqi/General-Unit-Test/results/python/fix_msbench_results.csv"  
df = pd.read_csv(csv_file)  
  
# 初始化新列为 None
if args.enable_generate:  
    df['coverage_before'] = None  
    df['coverage_after'] = None
if args.enable_error_fixing:
    df['errors_fixed'] = None
    df['coverage_after_fix'] = None
    # 为每轮修复添加覆盖率列
    for i in range(args.max_fix_iterations):
        df[f'coverage_iteration_{i+1}'] = None
        df[f'errors_fixed_iteration_{i+1}'] = None  
  
for index, row in tqdm(df.iterrows()):  
    image = row['image_tag']  
    image = "codeexecservice.azurecr.io/" + image  
    container_name = row['instance_id']  
  
    llm_client = CopilotProxyLLMClient(model=args.model)  
    if args.enable_generate:
        generator = CoverageBasedTestGenerator(  
            container_name=container_name,  
            images=image, 
            temp_dir=args.temp_dir,
            language=args.language,  
            llm_client=llm_client,  
            use_related_code_searcher=args.use_related_searcher  
        )  
    
        generated_tests, coverage_before = generator.generate_tests_for_project()  
        df.at[index, 'coverage_before'] = coverage_before.coverage_percentage if coverage_before is not None else None  
    
        if generated_tests:  
            generator.save_generated_tests(generated_tests)  
        coverage_after = generator.coverage_analyzer.collect_coverage()  
        df.at[index, 'coverage_after'] = coverage_after.coverage_percentage if coverage_after is not None else None  

    # 错误修复阶段
    if args.enable_error_fixing:
        print(f"Starting error fixing for {container_name}...")
        
        # 创建错误修复器
        error_fixer = create_error_fixer(
            container_name=container_name,
            docker_image=image,
            language=args.language,
            temp_dir=args.temp_dir,
            llm_client=llm_client,
            max_fix_iterations=args.max_fix_iterations
        )
        
        # 执行错误修复
        fix_results, coverage_after_fix, iteration_coverage_reports = error_fixer.fix_errors_and_collect_coverage()
        
        # 记录总体修复结果
        successful_fixes = [fix for fix in fix_results if fix.success]
        df.at[index, 'errors_fixed'] = len(successful_fixes)
        df.at[index, 'coverage_after_fix'] = coverage_after_fix.coverage_percentage if coverage_after_fix is not None else None
        
        # 记录每轮迭代的结果
        for iteration_report in iteration_coverage_reports:
            iteration_num = iteration_report['iteration']
            coverage_report = iteration_report['coverage_report']
            errors_fixed_in_iteration = iteration_report['errors_fixed']
            
            df.at[index, f'coverage_iteration_{iteration_num}'] = coverage_report.coverage_percentage if coverage_report is not None else None
            df.at[index, f'errors_fixed_iteration_{iteration_num}'] = errors_fixed_in_iteration
        
        print(f"Fixed {len(successful_fixes)}/{len(fix_results)} errors for {container_name}")
        print(f"Coverage progression: {[report['coverage_report'].coverage_percentage if report['coverage_report'] else 0 for report in iteration_coverage_reports]}")
    else:
        # 如果没有启用错误修复，将迭代列设为0
        for i in range(args.max_fix_iterations):
            df.at[index, f'coverage_iteration_{i+1}'] = None
            df.at[index, f'errors_fixed_iteration_{i+1}'] = 0
  
    print(f"Processed {container_name} with image {image} ...")  
  
# 写入 CSV  
df.to_csv(tgt_file, index=False)  