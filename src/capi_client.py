import requests
import json
import time
datetime = __import__('datetime')
from azure.identity import AzureCliCredential
from typing import List, Dict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class CopilotProxyLLMClient:
    """
    class CopilotProxyLLMClient: handles authentication and  query to the Copilot Proxy Chat API.
    """
    def __init__(
        self,
        integration_id: str = "autodev-test",
        proxy_url: str = "https://ces-dev1.azurewebsites.net/api/proxy/chat/completions",
        scope: str = "api://17b0ad65-ed36-4194-bb27-059c567bc41f/.default",
        model: str = "gpt-4o",
        timeout: int = 300,  # 增加默认超时时间到5分钟
        max_retries: int = 3,  # 最大重试次数
        backoff_factor: float = 1.0  # 重试间隔因子
    ):
        # Initialize credential and endpoint settings
        self.integration_id = integration_id
        self.proxy_url = proxy_url
        self.credential = AzureCliCredential()
        self.scope = scope
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        
        # Configure session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],  # HTTP状态码重试
            backoff_factor=backoff_factor,
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Acquire initial token
        token = self.credential.get_token(self.scope)
        self.bearer_token = token.token
        # Prepare static headers
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Copilot-Integration-Id": self.integration_id,
            "Authorization": f"Bearer {self.bearer_token}",
            "ces-proxy-target": "https://api.githubcopilot.com"
        }

    def set_timeout(self, timeout: int):
        """Set request timeout in seconds."""
        self.timeout = timeout
    
    def set_retry_config(self, max_retries: int = 3, backoff_factor: float = 1.0):
        """Update retry configuration."""
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        
        # Update session retry strategy
        retry_strategy = Retry(
            total=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=backoff_factor,
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def query_with_custom_timeout(self, message: List[Dict[str, str]], timeout: int) -> str:
        """
        Send a request with a custom timeout value.
        
        Args:
            message: The user message to send to the model.
            timeout: Custom timeout in seconds for this request.
            
        Returns:
            The response content from the LLM.
        """
        original_timeout = self.timeout
        try:
            self.timeout = timeout
            return self.query(message)
        finally:
            self.timeout = original_timeout

    def query(self, message: List[Dict[str, str]], retry_count: int = 0) -> str:
        """
        Send a chat completion request with the given message.

        Args:
            message: The user message to send to the model.
            retry_count: Current retry attempt (for internal use).

        Returns:
            The response content from the LLM.
        """
        # Optionally refresh the bearer token if needed
        token = self.credential.get_token(self.scope)
        self.headers["Authorization"] = f"Bearer {token.token}"

        # Build request body
        body = {
            "model": self.model,
            "messages": message
        }
        
        try:
            response = self.session.post(
                self.proxy_url,
                headers=self.headers,
                data=json.dumps(body),
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('choices', [{}])[0].get('message', {}).get('content', '')
            elif response.status_code in [429, 500, 502, 503, 504] and retry_count < self.max_retries:
                # 对于可重试的错误状态码，进行重试
                wait_time = self.backoff_factor * (2 ** retry_count)
                print(f"Request failed with status {response.status_code}, retrying in {wait_time} seconds... (attempt {retry_count + 1}/{self.max_retries})")
                time.sleep(wait_time)
                return self.query(message, retry_count + 1)
            else:
                raise RuntimeError(
                    f"Request failed [{response.status_code}]: {response.text}"
                )
                
        except requests.exceptions.Timeout as e:
            if retry_count < self.max_retries:
                wait_time = self.backoff_factor * (2 ** retry_count)
                print(f"Request timed out, retrying in {wait_time} seconds... (attempt {retry_count + 1}/{self.max_retries})")
                time.sleep(wait_time)
                return self.query(message, retry_count + 1)
            else:
                raise RuntimeError(f"Request timed out after {self.max_retries} retries. Original error: {str(e)}")
        
        except requests.exceptions.ConnectionError as e:
            if retry_count < self.max_retries:
                wait_time = self.backoff_factor * (2 ** retry_count)
                print(f"Connection error, retrying in {wait_time} seconds... (attempt {retry_count + 1}/{self.max_retries})")
                time.sleep(wait_time)
                return self.query(message, retry_count + 1)
            else:
                raise RuntimeError(f"Connection failed after {self.max_retries} retries. Original error: {str(e)}")
        
        except Exception as e:
            # 对于其他异常，如果还有重试次数，也尝试重试
            if retry_count < self.max_retries:
                wait_time = self.backoff_factor * (2 ** retry_count)
                print(f"Unexpected error: {str(e)}, retrying in {wait_time} seconds... (attempt {retry_count + 1}/{self.max_retries})")
                time.sleep(wait_time)
                return self.query(message, retry_count + 1)
            else:
                raise RuntimeError(f"Request failed after {self.max_retries} retries. Original error: {str(e)}")

# if __name__ == "__main__":
#     client = CopilotProxyLLMClient(model="claude-3.5-sonnet")
#     response = client.query([{"role": "user", "content": "1 * 220 =?"}])
#     print(response)