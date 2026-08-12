
from openai import OpenAI
from .model import BaseModel
from typing import Dict, List
from tenacity import retry, wait_random_exponential, stop_after_attempt
from utils import get_token

class APIModel(BaseModel):
    def __init__(self, model_name, base_url=None, api_key=None):
        default_api_key = None
        default_base_url = None
        if model_name in ['gemini-3-pro-preview','gpt-5.2-2025-12-11','o3-2025-04-16','gpt-4o-2024-11-20','gpt-4o-mini','o1-mini','o1-preview','gpt-4.5-preview']:
            default_api_key = get_token('xxx')
            default_base_url="https://xxxxxx"

        elif model_name.lower().__contains__('qwen'):
            if model_name in ['qwen3-vl-32b-instruct','qwen3-vl-32b-thinking',
                              'qwen3-vl-30b-a3b-instruct','qwen3-vl-30b-a3b-thinking',
                              'qwen3-vl-235b-a22b-instruct','qwen3-vl-235b-a22b-thinking',
                              'qwen2.5-vl-72b-instruct', 'qwen2.5-vl-32b-instruct']:
                default_api_key = get_token('bailian')
                default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            else:
                default_api_key = get_token('qwen')
                default_base_url="http://xxxx/v1"

        elif model_name.lower().__contains__('rotvl'):
            default_api_key = get_token('rotvl')
            default_base_url="http://xxxx/v1"

        elif base_url is None or api_key is None:
            raise ValueError(f"Unknown model type: {model_name}")

        if api_key is None:
            api_key = default_api_key
        if base_url is None:
            base_url = default_base_url

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        super().__init__(model_name)


    @retry(wait=wait_random_exponential(min=1, max=5), stop=stop_after_attempt(5))
    def generate_chat(
        self,
        messages: List,
        stop: List[str] = [],
        max_tokens: int = 2056,
        temperature=1,
        reasoning_effort="none"
    ):
        if self.model_name .__contains__('gpt-5') or self.model_name .__contains__('gemini-3'):
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_completion_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
                temperature=temperature,
            )
        else:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        return {
            'output': response.choices[0].message.content,
            'message': response.choices[0].message.model_dump(),
            'tokens_count': {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens
            }
        }
    
