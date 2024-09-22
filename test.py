import os
from dotenv import load_dotenv

load_dotenv()
print(f"User: {os.getenv('PG_USER')}, Password: {os.getenv('PG_PASSWORD')}, Host: {os.getenv('PG_HOST')}, Port: {os.getenv('PG_PORT')}")
