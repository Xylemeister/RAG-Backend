import os
import requests
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from vector_store import VectorStore
import PyPDF2
from datetime import datetime
import time

load_dotenv()

app = FastAPI()

vector_store = VectorStore()
vector_store.create_tables()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHATBOT_NAME = os.getenv("CHATBOT_NAME")
CHATBOT_PREPROMPT = f'namamu adalah {CHATBOT_NAME} ' + os.getenv("CHATBOT_PREPROMPT")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 200))
OVERLAP_SIZE = int(os.getenv("OVERLAP_SIZE", 20))
TOP_K = int(os.getenv("TOP_K", 5))
TOP_K_HISTORY = int(os.getenv("TOP_K_HISTORY", 3))

def start_counter():
    # Get the current time as the start time
    start_time = datetime.now()
    print(f"Counter started at {start_time.strftime('%H:%M:%S')}")

    return start_time

def end_counter(start_time):
    # Get the current time as the end time
    end_time = datetime.now()
    print(f"Counter ended at {end_time.strftime('%H:%M:%S')}")

    # Calculate the difference between start and end times
    elapsed_time = end_time - start_time
    print(f"Elapsed time: {elapsed_time}")



# Helper to extract text from PDF
def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ''
    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text += page.extract_text()
    return text

# Helper to get text embedding
def get_embedding(text):
    OPENAI_API_KEY= OPENAI_API_KEY
    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    data = {
        "model": "text-embedding-3-small",
        "input": text
    }
    response = requests.post(url, headers=headers, json=data)

    response_data = response.json()
    tokens_used = response_data['usage']['total_tokens']
    vector_store.store_token_count('embedding_input', tokens_used)
    return response_data['data'][0]['embedding']


# Helper to split text into chunks with overlap
def split_text_into_chunks(text, chunk_size, overlap_size):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap_size):
        chunk = ' '.join(words[i:i + chunk_size])
        chunks.append(chunk)
        if i + chunk_size >= len(words):
            break
    return chunks



# Helper to chat with OpenAI
def chat_with_openai(messages):
    OPENAI_API_KEY=OPENAI_API_KEY
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    data = {
        "model": "gpt-4o-mini",
        "messages": messages

    }
    #print(messages)
    
    #response = requests.post(url, headers=headers, json=data, stream=True)
    response = requests.post(url, headers=headers, json=data)

    #response_data = response
    response_data = response.json()
    #print(response_data['choices'][0]['message']['content'])
    
    #prompt_tokens = response_data['usage']['prompt_tokens']
    #completion_tokens = response_data['usage']['completion_tokens']
    
    #vector_store.store_token_count('completion_input', prompt_tokens)
    #vector_store.store_token_count('completion_output', completion_tokens)
    
    #return response_data['choices'][0]['message']['content']
    #print(response)

    return response_data

def chat_with_openai2(messages):
    OPENAI_API_KEY=OPENAI_API_KEY
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    data = {
        "model": "gpt-4o-mini",
        "messages": messages,
        "stream": True

    }
    #print(messages)
    
    response = requests.post(url, headers=headers, json=data, stream=True)
    #response = requests.post(url, headers=headers, json=data)

    #response_data = response
    response_data = response
    #print(response_data['choices'][0]['message']['content'])
    
    #prompt_tokens = response_data['usage']['prompt_tokens']
    #completion_tokens = response_data['usage']['completion_tokens']
    
    #vector_store.store_token_count('completion_input', prompt_tokens)
    #vector_store.store_token_count('completion_output', completion_tokens)
    
    #return response_data['choices'][0]['message']['content']
    #print(response)

    return response_data



@app.post("/upload-knowledge/")
async def upload_knowledge(file: UploadFile = File(...)):
    if file.content_type not in ["application/pdf", "text/plain"]:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    content = await file.read()
    if file.content_type == "application/pdf":
        content = extract_text_from_pdf(content)
    else:
        content = content.decode("utf-8")
    
    chunks = split_text_into_chunks(content, CHUNK_SIZE, OVERLAP_SIZE)

    for chunk in chunks:
        embedding = get_embedding(chunk)
        #vector_store.store_embedding(embedding, chunk, tokens_used=None)
    
    return {"message": "Knowledge uploaded and split into chunks successfully"}

@app.post("/newchat/")
async def newchat():
    messages = [{"role": "system", "content": CHATBOT_PREPROMPT}]
    session_id = vector_store.store_session(messages)
    return {"session_id": session_id}

@app.post("/chat/")
async def chat_with_session(session_id: int, text: str):
    print("-----------")
    session_id=1
    start_time = start_counter()
    session_history = vector_store.get_session(session_id)
    chat_embedding = get_embedding(text)
    end_counter(start_time)
    
    start_time = start_counter()
    # Retrieve top-k knowledge base results
    knowledge = vector_store.query_similar(chat_embedding, limit=TOP_K)
    knowledge_texts = [k[0] for k in knowledge]

    # Retrieve top-k relevant chat history within the session
    previous_chats = vector_store.query_chat_history(session_id, chat_embedding, limit=TOP_K_HISTORY)
    previous_chat_texts = [f"User: {chat[0]}\nAI: {chat[1]}" for chat in previous_chats]

    # Combine knowledge and previous chat history
    combined_context = "\n".join(knowledge_texts + previous_chat_texts)
    
    if combined_context:
        session_history.append({"role": "assistant", "content": combined_context})

    session_history.append({"role": "user", "content": text})
    end_counter(start_time)

    # Generate chat response
    start_time = start_counter()
    response_content = chat_with_openai2(session_history)
    end_counter(start_time)
    print(response_content)

    #response_content = chat_with_openai(text)
    
        
    #ai_answer_embedding = get_embedding(response_content)
    #return JSONResponse(content={"response": "ok"})

    #vector_store.store_chat_history(session_id, text, response_content, chat_embedding, ai_answer_embedding)
    #return JSONResponse(content={"response": response_content})
    #return JSONResponse(content={"response": response_content, "knowledge": knowledge_texts, "previous_chats": previous_chat_texts})
    return StreamingResponse(response_content.iter_content(chunk_size=1024), media_type="text/event-stream")
    

@app.get("/token-usage/")
async def token_usage(
    token_type: str,
    start_date: datetime = Query(..., description="Start date in the format YYYY-MM-DDTHH:MM:SS"),
    end_date: datetime = Query(..., description="End date in the format YYYY-MM-DDTHH:MM:SS")
):
    if token_type not in ["embedding_input", "completion_input", "completion_output"]:
        raise HTTPException(status_code=400, detail="Invalid token type. Valid types are 'embedding_input', 'completion_input', 'completion_output'.")
    
    tokens_used = vector_store.query_token_usage(token_type, start_date, end_date)
    return {"token_type": token_type, "tokens_used": tokens_used, "start_date": start_date, "end_date": end_date}


