
import torch
from typing import *

def support_bf16() -> bool:
    if not torch.cuda.is_available():
        return False
    
    major, minor = torch.cuda.get_device_capability()
    return (major >= 8) and (torch.cuda.is_bf16_supported())



