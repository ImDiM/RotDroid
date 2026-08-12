import json
import logging
from typing import Dict, List,Union
import re

def extract_defect_info(output: str) -> Union[Dict, None]:
    matches = re.findall(r"```json\s+({[\s\S]*?})\s*```", output)
    if len(matches) > 0:
        try:
            result = json.loads(matches[0])
            return result
        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing failure: {e}")
    else:
        return None
    
