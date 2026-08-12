
from typing import List, Dict, Any, Union
import torch
from .model import BaseModel
from utils import support_bf16


class VllmModel(BaseModel):
    def __init__(
            self,
            model_name: str,
            name: str = 'name',
            description: str = 'description',
            max_model_len: int = 8192,
            dtype: str = None,
            **vllm_args
    ):
        from vllm import LLM
        gpus = torch.cuda.device_count()
        if not dtype:
            dtype=torch.bfloat16 if support_bf16() else torch.float16
        self.name = name
        self.description = description

        self.model_name = model_name
        self.model = LLM(
            model=model_name,
            max_model_len=max_model_len,
            dtype=dtype,
            tensor_parallel_size=gpus,

            **vllm_args
        )

    def generate_chat(
            self,
            messages: Union[List[List[Dict]], List[Dict]],
            tools: List[Dict[str, Any]] = None,
            max_tokens: int = 1024,
            temperature: float = 0.1,
            top_p: float = 1.0,
            stop_strs: List[str] = None,
            stream: bool = False,
            **generation_args
    ) -> Dict[str, List]:
        from vllm import SamplingParams
        
        assert len(messages) > 0

        params = SamplingParams(            
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p
        )
        res = self.model.chat(
            messages=messages,
            sampling_params=params,
            tools=tools, 
            use_tqdm=False,
            **generation_args
        )

        return {
            "output": res[0].outputs[0].text,
            "tokens_count": {
                "prompt_tokens": len(res[0].prompt_token_ids),
                "completion_tokens": len(res[0].outputs[0].token_ids),
            }
        }
        
        
