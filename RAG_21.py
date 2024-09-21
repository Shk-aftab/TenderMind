import os
import requests
import cohere
import yaml
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores.faiss import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_cohere import CohereEmbeddings  # Updated import
from dotenv import load_dotenv  # Optional, for loading environment variables

# Load environment variables from .env file (optional)
load_dotenv()

# Initialize Cohere Client
COHERE_API_KEY = os.getenv('COHERE_API_KEY')  # Ensure this environment variable is set
if not COHERE_API_KEY:
    raise ValueError("COHERE_API_KEY environment variable not set.")
cohere_client = cohere.Client(COHERE_API_KEY)

def download_file(url, save_path='downloaded_file.pdf'):
    """
    Download a file from a given URL and save it.
    """
    response = requests.get(url)
    response.raise_for_status()  # Raise an error for bad status
    with open(save_path, 'wb') as f:
        f.write(response.content)
    print("File downloaded successfully!")
    return save_path

def convert_to_vector_store(file_path):
    """
    Convert a file to a vector store.
    """
    loader = PyPDFLoader(file_path)
    embedding = CohereEmbeddings(model="embed-english-light-v3.0")
    pages = loader.load()
    split_text = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=10,
        length_function=len,
        is_separator_regex=False,
    )
    split_pages = split_text.split_documents(pages)
    db = FAISS.from_documents(split_pages, embedding=embedding)
    return db

def save_vector_store(db, save_path):
    """
    Save the vector store to a local directory.
    """
    db.save_local(folder_path=save_path)
    print(f"Vector store saved successfully at {save_path}")

def load_vector_store(save_path, embedding):
    """
    Load the vector store from a local directory.
    """
    db = FAISS.load_local(save_path, embeddings=embedding, allow_dangerous_deserialization=True)
    return db

def query_vector_store(db, query, top_k=5):
    """
    Query the vector store and return top_k similar documents.
    """
    results = db.similarity_search(query, k=top_k)
    return results

def generate_structured_yaml(retrieved_text):
    """
    Use Cohere's language model to parse retrieved text into structured YAML.
    Saves the raw YAML for debugging if it's malformed.
    """
    prompt = f"""
    Extract the following information from the tender document and structure it into the specified YAML format. If any field is not available, set its value to "Not Provided".

    ### Retrieved Text:
    {retrieved_text}

    ### YAML Structure:
    Overview:
      Tender Title: "value"
      Issuing Company: "value"
      Deadline: "value"
      Reference Number: "value"
    Cost Information:
      Budget Information: "value"
      Payment Terms: "value"
      Cost Breakdown: "value"
    Key Objectives: "value"
    General Requirements: "value"
    Special Requirements: "value"
    Phases and Milestones: "value"
    Submission Guidelines: "value"
    Technical Specifications: "value"
    Legal and Compliance Requirements: "value"
    Support and Maintenance: "value"
    Project Team and Qualifications: "value"
    Contact Information:
      Name: "value"
      Email: "value"
      Phone: "value"
      Address: "value"
    """

    try:
        response = cohere_client.generate(
            model='command-xlarge-nightly',  # Use the latest capable model
            prompt=prompt,
            max_tokens=1500,  # Increased token limit to accommodate longer YAML
            temperature=0.2,
            stop_sequences=["}"]
        )
        generated_text = response.generations[0].text.strip()

        # Save the raw YAML to a file for debugging
        raw_yaml_path = "output/raw_generated_yaml.yaml"
        os.makedirs(os.path.dirname(raw_yaml_path), exist_ok=True)
        with open(raw_yaml_path, 'w', encoding='utf-8') as f:
            f.write(generated_text)
        print(f"Raw YAML saved at {raw_yaml_path}")

        try:
            # Parse the YAML to ensure it's valid
            structured_yaml = yaml.safe_load(generated_text)
            return structured_yaml
        except yaml.YAMLError as ye:
            print(f"YAMLDecodeError: {ye}")
            # Save the malformed YAML for debugging
            malformed_yaml_path = "output/malformed_yaml.yaml"
            with open(malformed_yaml_path, 'w', encoding='utf-8') as f:
                f.write(generated_text)
            print(f"Malformed YAML saved at {malformed_yaml_path}")
            return {}
    except Exception as e:
        print(f"Error generating YAML: {e}")
        return {}

# Example usage
if __name__ == "__main__":
    # Optionally, download a PDF file
    # url = "https://example.com/path/to/your/tender.pdf"
    # file_path = download_file(url)

    # Load a PDF file from local directory
    file_path = r"beispiel\CPQ Ausschreibung 3.pdf"  # Use raw string to handle backslashes

    # Convert the file to a vector store
    db = convert_to_vector_store(file_path)

    # Save the vector store
    save_path = "store/vectorstore"
    save_vector_store(db, save_path)

    # Load the vector store
    embedding = CohereEmbeddings(model="embed-english-light-v3.0")
    db = load_vector_store(save_path, embedding)

    # Query the vector store
    query = "What are important things in the tender?"
    results = query_vector_store(db, query, top_k=5)

    # Combine retrieved texts
    retrieved_text = "\n".join([doc.page_content for doc in results])

    # Generate structured YAML
    structured_data = generate_structured_yaml(retrieved_text)

    # Print the structured YAML
    if structured_data:
        print(yaml.dump(structured_data, sort_keys=False, indent=4))
    else:
        print("Failed to generate structured YAML.")
