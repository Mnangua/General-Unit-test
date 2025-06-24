import subprocess  
import pandas as pd  
from src.generate.unit_test_generator import CoverageBasedTestGenerator  
from src.capi_client import CopilotProxyLLMClient  
import argparse  
from tqdm import tqdm  
  
parser = argparse.ArgumentParser(description="Generate tests on msbench")  
parser.add_argument("--temp-dir", default="./docker_output/related_code_postprocess_exp", help="Temporary directory for test generation")
parser.add_argument("--language", choices=["python", "java"], help="Programming language")  
parser.add_argument("--model", default="claude-3.5-sonnet", help="LLM model to use")  
parser.add_argument("--use-related-searcher", action="store_true",  
                    help="Use related code searcher for better context")  
args = parser.parse_args()  
  
csv_file = "/home/mengnanqi/General-Unit-Test/benchmark/python-generate-test/test_metadata.csv"  
df = pd.read_csv(csv_file)  
    
for index, row in tqdm(df.iterrows()):  
    image = row['image_tag']  
    image = "codeexecservice.azurecr.io/" + image  
    container_name = row['instance_id']  
  
    llm_client = CopilotProxyLLMClient(model=args.model)  
    generator = CoverageBasedTestGenerator(  
        container_name=container_name,  
        images=image, 
        temp_dir=args.temp_dir,
        language=args.language,  
        llm_client=llm_client,  
        use_related_code_searcher=args.use_related_searcher  
    )  
  
    coverage_report = generator.coverage_analyzer.collect_coverage()  

    print(f"Processed {container_name} with image {image} ...")  
    if coverage_report:
        print(f"Coverage for {container_name}: {coverage_report.coverage_percentage:.2f}%")
        print(f"Coverage Test Output: {coverage_report.tests_output.strip()}")
    else:
        print(f"No coverage report available for {container_name}.")
  