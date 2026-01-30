from vertexai.preview.generative_models import GenerativeModel
import vertexai
import os
from dotenv import load_dotenv

load_dotenv()



vertexai.init(
    project=os.environ["GOOGLE_CLOUD_PROJECT_ID"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"]
)
GEMINI_MODEL_NAME="gemini-2.5-pro"
print(f"GOOGLE_CLOUD_PROJECT_ID { os.getenv('GOOGLE_CLOUD_PROJECT_ID')}")
print(f"GOOGLE_CLOUD_LOCATION { os.getenv('GOOGLE_CLOUD_LOCATION')}")
print(f"GEMINI_MODEL_NAME { os.getenv('GEMINI_MODEL_NAME')}")

model = GenerativeModel(GEMINI_MODEL_NAME)
response = model.generate_content("Say hello from Gemini")
print(response.text)
