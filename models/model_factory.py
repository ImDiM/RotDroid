
from .vllm_models import VllmModel
from typing import Dict
from .api_models import APIModel

class ModelFactory:
    @staticmethod
    def vllm_model(config_model:Dict):
        model_name = config_model["name"]
        vllm_args={
            'limit_mm_per_prompt':{"image":config_model["image_count"]}
        }
        return VllmModel(model_name=model_name,**vllm_args)


    @staticmethod
    def api_model(config_model:Dict):
        model_name = config_model["name"]
        return APIModel(
            model_name=model_name,
            base_url=config_model.get("base_url"),
            api_key=config_model.get("api_key"),
        )

        
