from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from transformers import T5ForConditionalGeneration, T5Tokenizer
import faiss
import numpy as np
import re
import pytesseract
from PIL import Image
import fitz  # PyMuPDF
import os
import io
import torch
import requests
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import spacy
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient  # MongoDB async driver

# Load environment variables
load_dotenv()

app = FastAPI()

# ---------------------------- CORS Setup ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (change to frontend URL in production)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (POST, GET, etc.)
    allow_headers=["*"],  # Allow all headers
)

# ---------------------------- MongoDB Configuration ----------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = "legal_assistant"

client = AsyncIOMotorClient(MONGO_URI)
db = client[DATABASE_NAME]

class TestDocument(BaseModel):
    name: str
    description: str

class QuestionRequest(BaseModel):
    question: str

# ---------------------------- Load Models ----------------------------
embedding_model = SentenceTransformer('all-mpnet-base-v2', device="cuda" if torch.cuda.is_available() else "cpu")
nlp = spacy.load("en_core_web_sm")

model_name = "google/flan-t5-small"
device = "cuda" if torch.cuda.is_available() else "cpu"
model = T5ForConditionalGeneration.from_pretrained(model_name).to(device)
tokenizer = T5Tokenizer.from_pretrained(model_name, legacy=False)

# ---------------------------- FAISS Setup ----------------------------
embedding_dim = 768
faiss_index = faiss.IndexFlatL2(embedding_dim)
document_store = {}

# ---------------------------- Gemini API Setup ----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing. Please set it as an environment variable.")

# ---------------------------- Utility Functions ----------------------------

def clean_and_limit_text(text: str, max_tokens: int = 700) -> str:
    text = re.sub(r'[^\w\s]', '', text)
    doc = nlp(text)
    filtered_words = [token.lemma_ for token in doc if not token.is_stop]
    return ' '.join(filtered_words[:max_tokens])

def extract_text_from_file(file: UploadFile) -> str:
    text = ""
    try:
        file_content = file.file.read()  # Read file content

        if file.filename.endswith(".pdf"):
            pdf_doc = fitz.open(stream=file_content, filetype="pdf")
            text = " ".join([page.get_text("text") for page in pdf_doc])

        elif file.filename.endswith((".png", ".jpg", ".jpeg")):
            image = Image.open(io.BytesIO(file_content))  # Ensure the image is read correctly
            text = pytesseract.image_to_string(image)  # Extract text from image

        else:
            raise HTTPException(status_code=400, detail="Unsupported file format.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

    return clean_and_limit_text(text)


async def add_document_to_storage(text: str, filename: str):
    embedding = embedding_model.encode([text], convert_to_numpy=True)
    faiss_index.add(embedding)
    index_id = len(document_store)
    document_store[index_id] = text

    await db.documents.insert_one({"filename": filename, "text": text, "embedding": embedding.tolist()})

async def retrieve_similar_texts(query: str, top_k: int = 3) -> str:
    query_embedding = embedding_model.encode([query], convert_to_numpy=True)

    if faiss_index.ntotal == 0:
        return ""

    distances, indices = faiss_index.search(query_embedding, top_k)
    retrieved_texts = [document_store[idx] for idx in indices[0] if idx in document_store]

    return " ".join(retrieved_texts)

async def call_gemini_api(question: str, context: str = "") -> str:
    headers = {"Content-Type": "application/json"}
    prompt = f"Use the following legal context to answer the question.\n\nContext: {context}\n\nQuestion: {question}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 200}
    }
    try:
        response = requests.post(f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", headers=headers, json=payload)
        response.raise_for_status()
        return response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
    except requests.RequestException as e:
        print(f"Gemini API Error: {e}")
        return None

async def generate_answer(question: str) -> str:
    context = await retrieve_similar_texts(question)
    gemini_response = await call_gemini_api(question, context)

    if gemini_response:
        answer = gemini_response
    else:
        input_text = f"question: {question} context: {context}"
        inputs = tokenizer(input_text, return_tensors="pt").to(device)
        outputs = model.generate(inputs["input_ids"], max_length=200)
        answer = tokenizer.decode(outputs[0], skip_special_tokens=True)

    await db.queries.insert_one({"question": question, "answer": answer, "context": context})
    
    return answer

# ---------------------------- FastAPI Endpoints ----------------------------

@app.post("/upload-legal-doc/")
async def upload_legal_doc(file: UploadFile = File(...)):
    try:
        extracted_text = extract_text_from_file(file)
        await add_document_to_storage(extracted_text, file.filename)
        return {"message": "Document processed and indexed successfully!","filename":file.filename, "extracted_text": extracted_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.post("/chatbot/")
async def answer_legal_question(request: QuestionRequest):
    response = await generate_answer(request.question)
    return {"answer": response}

@app.post("/extract-text/")
async def extract_text(file: UploadFile = File(...)):
    extracted_text = extract_text_from_file(file)
    return {"extracted_text": extracted_text}

@app.post("/test-mongo/")
async def test_mongo_connection(data: TestDocument):
    try:
        collection = db["test_collection"]
        result = await collection.insert_one(data.dict())
        
        inserted_doc = await collection.find_one({"_id": result.inserted_id})
        if inserted_doc and "_id" in inserted_doc:
            inserted_doc["_id"] = str(inserted_doc["_id"])

        return {"message": "MongoDB is connected!", "inserted_document": inserted_doc}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MongoDB connection failed: {str(e)}")
