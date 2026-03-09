import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

def get_llm():
    return OpenAI(
        base_url=os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )
