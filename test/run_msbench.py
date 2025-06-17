import subprocess  
import pandas as pd  
from src.generate.unit_test_generator import CoverageBasedTestGenerator  
from src.capi_client import CopilotProxyLLMClient  
import argparse  
from tqdm import tqdm  
  
parser = argparse.ArgumentParser(description="Generate tests on msbench")  
parser.add_argument("--language", choices=["python", "java"], help="Programming language")  
parser.add_argument("--model", default="claude-3.5-sonnet", help="LLM model to use")  
parser.add_argument("--use-related-searcher", action="store_true",  
                    help="Use related code searcher for better context")  
args = parser.parse_args()  
  
csv_file = "/home/mengnanqi/General-Unit-Test/benchmark/python-generate-test/metadata_related_code.csv"  
tgt_file = "/home/mengnanqi/General-Unit-Test/results/python/related_code_msbench_results.csv"  
df = pd.read_csv(csv_file)  
  
# 初始化新列为 None  
df['coverage_before'] = None  
df['coverage_after'] = None  
  
for index, row in tqdm(df.iterrows()):  
    image = row['image_tag']  
    image = "codeexecservice.azurecr.io/" + image  
    container_name = row['instance_id']  
  
    llm_client = CopilotProxyLLMClient(model=args.model)  
    generator = CoverageBasedTestGenerator(  
        container_name=container_name,  
        images=image,  
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
  
    print(f"Processed {container_name} with image {image} ...")  
  
# 写入 CSV  
df.to_csv(tgt_file, index=False)  