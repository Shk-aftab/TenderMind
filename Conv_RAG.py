import os
import yaml
import cohere
from langchain_community.vectorstores.faiss import FAISS
from langchain_cohere import CohereEmbeddings
from dotenv import load_dotenv
from typing import List, Dict, Optional

# Load environment variables from .env file (optional)
load_dotenv()

# Initialize Cohere Client
COHERE_API_KEY = os.getenv('COHERE_API_KEY')  # Ensure this environment variable is set
if not COHERE_API_KEY:
    raise ValueError("COHERE_API_KEY environment variable not set.")
cohere_client = cohere.Client(COHERE_API_KEY)

# Load the YAML structured data
def load_yaml(yaml_path: str) -> Dict:
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data

# Load the vector store
def load_vector_store(save_path: str, embedding_model: str) -> FAISS:
    embedding = CohereEmbeddings(model=embedding_model)
    db = FAISS.load_local(save_path, embeddings=embedding, allow_dangerous_deserialization=True)
    return db

# Conversation management class
class Conversation:
    def __init__(self, topic: str, initial_context: str, db: FAISS):
        self.topic = topic
        self.context: List[str] = [f"Topic: {topic}", f"Initial Context: {initial_context}"]
        self.db = db

    def add_to_context(self, message: str):
        self.context.append(message)
        # Limit context to last N messages to prevent it from growing indefinitely
        if len(self.context) > 20:
            self.context = self.context[-20:]

    def get_full_context(self) -> str:
        return "\n".join(self.context)

    def generate_response(self, user_query: str) -> str:
        # Add user query to context
        self.add_to_context(f"User: {user_query}")

        # Retrieve relevant documents based on the user query
        search_query = user_query  # Only use the latest user query for retrieval
        results = self.db.similarity_search(search_query, k=5)
        retrieved_text = "\n".join([doc.page_content for doc in results])

        # Prepare the prompt with context and retrieved documents, including guardrails
        prompt = f"""
You are an AI assistant specialized in providing information based on the provided documents.

- **Stay on Topic**: Only provide information that is directly related to the selected topic.
- **Use Provided Information**: Base all your answers solely on the retrieved documents and the ongoing conversation context.
- **No Assumptions**: If the information is not available in the provided documents, respond with "Not Provided".
- **Conciseness**: Provide clear and concise answers without unnecessary elaboration.

### Retrieved Information:
{retrieved_text}

### Conversation Context:
{self.get_full_context()}

### Response:
"""

        try:
            response = cohere_client.generate(
                model='command-xlarge-nightly',  # Use the latest capable model
                prompt=prompt,
                max_tokens=500,
                temperature=0.3,
                stop_sequences=["\nUser:", "\nAI:"]
            )
            ai_response = response.generations[0].text.strip()
            # Add AI response to context
            self.add_to_context(f"AI: {ai_response}")
            return ai_response
        except Exception as e:
            print(f"Error generating response: {e}")
            return "I'm sorry, I couldn't process your request at the moment."

# Chat Manager to handle multiple conversations
class ChatManager:
    def __init__(self, vector_store_path: str, embedding_model: str, yaml_path: str):
        self.db = load_vector_store(vector_store_path, embedding_model)
        self.yaml_data = load_yaml(yaml_path)
        self.conversations: Dict[str, Conversation] = {}  # key: topic, value: Conversation instance

    def start_conversation(self, topic_key: str) -> str:
        if topic_key not in self.yaml_data:
            return f"The topic '{topic_key}' does not exist in the YAML data."

        initial_context = self.yaml_data.get(topic_key, "Not Provided")
        if isinstance(initial_context, dict):
            # Convert nested dict to string
            initial_context = yaml.dump(initial_context, sort_keys=False, allow_unicode=True)
        elif isinstance(initial_context, list):
            initial_context = "\n".join(initial_context)
        else:
            initial_context = str(initial_context)

        conversation = Conversation(topic=topic_key, initial_context=initial_context, db=self.db)
        self.conversations[topic_key] = conversation
        return f"Conversation started on topic: {topic_key}"

    def send_message(self, topic_key: str, user_message: str) -> str:
        if topic_key not in self.conversations:
            return f"No active conversation for topic '{topic_key}'. Please start a conversation first."

        conversation = self.conversations[topic_key]
        ai_response = conversation.generate_response(user_message)
        return ai_response

    def end_conversation(self, topic_key: str) -> str:
        if topic_key in self.conversations:
            del self.conversations[topic_key]
            return f"Conversation on topic '{topic_key}' has been ended."
        else:
            return f"No active conversation for topic '{topic_key}'."

    def list_topics(self) -> List[str]:
        return list(self.yaml_data.keys())

    def get_conversation_context(self, topic_key: str) -> Optional[str]:
        if topic_key in self.conversations:
            return self.conversations[topic_key].get_full_context()
        return None

# Example usage
# You can import ChatManager from this module and use it within your Flask routes.

# from flask import Flask, request, jsonify
# from Conv_RAG import ChatManager

# app = Flask(__name__)

# Initialize ChatManager
# vector_store_path = "store/vectorstore"
# embedding_model = "embed-multilingual-v2.0"  # Use the same multilingual model
# yaml_path = "output/raw_generated_yaml.yaml"  # Path to your generated YAML
# chat_manager = ChatManager(vector_store_path, embedding_model, yaml_path)