class BaseModel:
    def __init__(self, model_name) -> None:
        self.model_name=model_name

    def generate_chat(self, messages, temperature=0.2, max_tokens=500):
        pass