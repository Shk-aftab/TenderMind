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
    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"YAML file not found at path: {yaml_path}")
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data

# Load the vector store
def load_vector_store(save_path: str, embedding_model: str) -> FAISS:
    if not os.path.exists(save_path):
        raise FileNotFoundError(f"Vector store not found at path: {save_path}")
    embedding = CohereEmbeddings(model=embedding_model)
    # Removed allow_dangerous_deserialization=True for security reasons
    db = FAISS.load_local(save_path, embeddings=embedding, allow_dangerous_deserialization=True)
    return db

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

    def generate_response(self, user_query: str) -> Dict:
        """
        Generate a response based on the user's query and retrieve reference lines from the vector database.
        Returns a structured response containing the AI's response and reference lines.
        """
        # Add user query to context
        self.add_to_context(f"User: {user_query}")

        # Retrieve relevant documents based on the user query
        search_query = user_query  # Only use the latest user query for retrieval
        results = self.db.similarity_search(search_query, k=5)
        retrieved_texts = [doc.page_content for doc in results]

        # Assign page numbers based on the order of retrieved documents
        # This assumes that the first result is Page 1, second is Page 2, etc.
        references = []
        for idx, doc in enumerate(results):
            page_number = idx + 1
            snippet = self.extract_snippet(doc.page_content)
            references.append(f"Page {page_number}: {snippet}")

        # Format retrieved texts with separation
        formatted_retrieved_texts = '\n---\n'.join(retrieved_texts)

        # Format references as a numbered list
        formatted_references = '\n'.join([f"{ref}" for ref in references])

        prompt = f"""You are an AI assistant specialized in providing information based on the provided documents.

- **Stay on Topic**: Only provide information that is directly related to the selected topic.
- **Use Provided Information**: Base all your answers solely on the retrieved documents and the ongoing conversation context.
- **No Assumptions**: If the information is not available in the provided documents, respond with "Not Provided".
- **Conciseness**: Provide clear and concise answers without unnecessary elaboration.
- **Cite References**: At the end of your response, list the references numbers that were used from the retrieved documents in the format [1], [2], etc.

### Retrieved Information:
{formatted_retrieved_texts}

### Conversation Context:
{self.get_full_context()}

### Response:
"""

        try:
            # Generate the response using the Cohere API
            response = cohere_client.generate(
                model='command-xlarge-nightly',  # Ensure this model is correct and accessible
                prompt=prompt,
                max_tokens=500,
                temperature=0.3,
                stop_sequences=["\nUser:", "\nAI:"]
            )
            ai_response = response.generations[0].text.strip()

            # Add AI response to context
            self.add_to_context(f"AI: {ai_response}")

            # Create the structured response
            response_data = {
                "ai_response": ai_response,
                "references": formatted_references  # Formatted references as a string
            }

            return response_data

        except Exception as e:
            print(f"Error generating response: {e}")
            return {
                "ai_response": "I'm sorry, I couldn't process your request at the moment.",
                "references": ""
            }

    def extract_snippet(self, text: str, max_length: int = 100) -> str:
        """
        Extract a snippet from the text for referencing.
        If the text is longer than max_length, truncate it and add ellipsis.
        """
        if len(text) <= max_length:
            return text
        else:
            # Find the last space before max_length to avoid cutting words
            snippet = text[:max_length].rsplit(' ', 1)[0]
            return snippet + '...'

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

    def send_message(self, topic_key: str, user_message: str) -> Dict[str, str]:
        if topic_key not in self.conversations:
            return {"error": f"No active conversation for topic '{topic_key}'. Please start a conversation first."}

        conversation = self.conversations[topic_key]
        response_data = conversation.generate_response(user_message)
        ai_response = response_data.get('ai_response', '')
        references = response_data.get('references', '')

        # Format references
        if references:
            references_string = references
        else:
            references_string = 'No references available.'

        return {"ai_response": ai_response, "references": references_string}

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

class ChatWithoutTopic:
    """Class for conversations without specifying a topic."""
    def __init__(self, vector_store_path: str, embedding_model: str):
        self.db = load_vector_store(vector_store_path, embedding_model)
        self.conversation = Conversation(topic="general", initial_context="This is a general conversation.", db=self.db)

    def start_conversation(self) -> str:
        return "Conversation started on general topic."

    def send_message(self, user_message: str) -> Dict[str, str]:
        response_data = self.conversation.generate_response(user_message)
        ai_response = response_data.get('ai_response', '')
        references = response_data.get('references', '')
        if references:
            references_string = references
        else:
            references_string = 'No references available.'
        return {"ai_response": ai_response, "references": references_string}

    def end_conversation(self) -> str:
        # Reset the conversation to initial state
        self.conversation = Conversation(topic="general", initial_context="This is a general conversation.", db=self.db)
        return "Conversation on general topic has been ended."

    def get_conversation_context(self) -> str:
        return self.conversation.get_full_context()

if __name__ == "__main__":
    # Example usage
    vector_store_path = "store/vectorstore"
    embedding_model = "embed-multilingual-v2.0"
    yaml_path = "uploads/structured_tender_CPQ_Ausschreibung2.yaml"

    # Initialize Chat Manager for topic-based conversations
    chat_manager = ChatManager(vector_store_path, embedding_model, yaml_path)
    
    # # Start a conversation on a specific topic
    topic = "Übersicht"  # Replace with an actual topic key from your YAML
    print(chat_manager.start_conversation(topic))
    
    # # Send a message in the conversation
    user_query = "What is the topic about?"
    response = chat_manager.send_message(topic, user_query)
    print("AI Response:", response["ai_response"])
    print("References:\n", response["references"])
    
    # # End the conversation
    print(chat_manager.end_conversation(topic))
    
    # # List available topics
    print("Available Topics:", chat_manager.list_topics())
    
    # # Get conversation context (should be None after ending)
    context = chat_manager.get_conversation_context(topic)
    if context:
        print("Conversation Context:\n", context)
    else:
        print(f"No active conversation for topic '{topic}'.")
    
    print("\n---\n")
    
    # Initialize ChatWithoutTopic for general conversations
    chat_manager_general = ChatWithoutTopic(vector_store_path, embedding_model)
    print(chat_manager_general.start_conversation())
    general_query = "can you get an educated gues for the revenue potential of this tender?, like I know its not provided but still if you had to take guess what would you say"
    general_response = chat_manager_general.send_message(general_query)
    print("AI Response:", general_response["ai_response"])
    print("References:\n", general_response["references"])
    print(chat_manager_general.end_conversation())
    print("Conversation Context:\n", chat_manager_general.get_conversation_context())
