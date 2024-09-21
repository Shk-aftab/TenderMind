import os
import requests
import cohere
import yaml
import re
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores.faiss import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_cohere import CohereEmbeddings
from dotenv import load_dotenv

# Load environment variables from .env file (optional)
load_dotenv()

# Initialize Cohere Client
COHERE_API_KEY = os.getenv('COHERE_API_KEY')
if not COHERE_API_KEY:
    raise ValueError("COHERE_API_KEY environment variable not set.")
cohere_client = cohere.Client(COHERE_API_KEY)


def download_file(url, save_path='downloaded_file.pdf'):
    response = requests.get(url)
    response.raise_for_status()  # Raise an error for bad status
    with open(save_path, 'wb') as f:
        f.write(response.content)
    print("File downloaded successfully!")
    return save_path

def preprocess_text(text):
    """
    Preprocess text to remove unnecessary line breaks and improve context understanding.
    """
    # Remove multiple newlines and extra spaces
    text = re.sub(r'\n+', ' ', text)  # Replace multiple newlines with a single space
    text = re.sub(r'\s+', ' ', text).strip()  # Remove extra spaces

    # Remove common headers or footers (e.g., "Page 1", "Ausschreibungsdokument", etc.)
    text = re.sub(r'Page \d+', '', text)
    text = re.sub(r'Ausschreibungsdokument.*', '', text)

    # Fix sentence-breaking by handling cases where a sentence is split across lines without a period
    text = re.sub(r'([a-z])-\s+([a-z])', r'\1\2', text)  # Fix hyphenated word breaks
    text = re.sub(r'(\S)- (\S)', r'\1\2', text)  # Handle more hyphen breaks in German
    text = re.sub(r'([a-zA-Z])\s*\n\s*([a-zA-Z])', r'\1 \2', text)  # Remove line breaks within sentences

    return text


def convert_to_vector_store(file_path):
    loader = PyPDFLoader(file_path)
    # Use an embedding model suitable for German (if available)
    embedding = CohereEmbeddings(model="embed-multilingual-v2.0")  # Updated to a multilingual model
    pages = loader.load()

    # Preprocess each page's content before saving to the database
    preprocessed_pages = []
    for page in pages:
        preprocessed_content = preprocess_text(page.page_content)
        preprocessed_pages.append(preprocessed_content)

    # Save preprocessed pages to a text file for debugging purposes
    pages_text_path = "output/pages_preprocessed.txt"
    os.makedirs(os.path.dirname(pages_text_path), exist_ok=True)

    with open(pages_text_path, 'w', encoding='utf-8') as f:
        for i, content in enumerate(preprocessed_pages):
            f.write(f"Page {i + 1}:\n")
            f.write(content)
            f.write("\n\n" + "-" * 50 + "\n\n")  # Adding a separator between pages

    print(f"Preprocessed pages content saved for debugging at {pages_text_path}")

    # Initialize the RecursiveCharacterTextSplitter
    split_text = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=10,
        length_function=len,
        is_separator_regex=False,
    )

    # Split the preprocessed pages and store them in the vector store
    split_pages = []
    for content in preprocessed_pages:
        split_pages.extend(split_text.split_text(content))  # Splitting each page individually

    # Create vector store from split pages
    db = FAISS.from_texts(split_pages, embedding=embedding)

    return db


def save_vector_store(db, save_path):
    db.save_local(folder_path=save_path)
    print(f"Vector store saved successfully at {save_path}")


def load_vector_store(save_path, embedding):
    db = FAISS.load_local(save_path, embeddings=embedding, allow_dangerous_deserialization=True)
    return db


def query_vector_store(db, query, top_k=5):
    results = db.similarity_search(query, k=top_k)
    return results


def generate_structured_yaml(retrieved_text):
    prompt = f"""
    Extrahiere die folgenden Informationen aus dem Ausschreibungsdokument und strukturiere sie in das angegebene YAML-Format. Achte besonders darauf, die *Projektphasen mit Zeitangaben* und *Kontaktinformationen* zu extrahieren. Gib das Ergebnis ohne zusätzliche Formatierung oder Codeblöcke aus. Wenn ein Feld nicht verfügbar ist, setze seinen Wert auf "Nicht angegeben".

    ### Auszugsweiser Text:
    {retrieved_text}

    ### YAML-Struktur:

    Übersicht:
      Ausschreibungstitel: "value"
      Ausschreibende Firma: "value"
      Abgabefrist: "value"
      Referenznummer: "value"
    Kosteninformationen:
      Budgetinformationen: "value"
      Zahlungsbedingungen: "value"
      Kostenaufgliederung: "value"
    Hauptziele: "value"
    Allgemeine Anforderungen: "value"
    Besondere Anforderungen: "value"
    Phasen und Meilensteine: 
      - Anforderungsanalyse: "value"
      - Design und Architekturplanung: "value"
      - Entwicklung & Implementierung: "value"
      - Testphase: "value"
      - Schulung und Einführung: "value"
      - Abnahme und Übergabe: "value"
    Einreichungsrichtlinien: "value"
    Technische Spezifikationen: "value"
    Rechtliche und Compliance-Anforderungen: "value"
    Support und Wartung: "value"
    
    . und Qualifikationen: "value"
    Kontaktinformationen:
      Name: "value"
      E-Mail: "value"
      Telefon: "value"
      Adresse: "value"
    """

    # Proceed with the rest of the generation process...

    try:
        response = cohere_client.generate(
            model='command-xlarge-nightly',
            prompt=prompt,
            max_tokens=1500,
            temperature=0.3,
            k=5,
            stop_sequences=["}"]
        )
        generated_text = response.generations[0].text.strip()

        # Remove code block delimiters if present
        if generated_text.startswith("yaml"):
            generated_text = generated_text[len("yaml"):].strip()
        if generated_text.endswith(""):
            generated_text = generated_text[:-len("")].strip()

        # Saving raw YAML to a file while handling UTF-8 characters correctly
        raw_yaml_path = "output/raw_generated_yaml.yaml"
        os.makedirs(os.path.dirname(raw_yaml_path), exist_ok=True)
        with open(raw_yaml_path, 'w', encoding='utf-8') as f:
            f.write(generated_text)
        print(f"Raw YAML saved at {raw_yaml_path}")

        try:
            structured_yaml = yaml.safe_load(generated_text)
            return structured_yaml
        except yaml.YAMLError as ye:
            print(f"YAMLDecodeError: {ye}")
            malformed_yaml_path = "output/malformed_yaml.yaml"
            with open(malformed_yaml_path, 'w', encoding='utf-8') as f:
                f.write(generated_text)
            print(f"Malformed YAML saved at {malformed_yaml_path}")
            return {}
    except Exception as e:
        print(f"Error generating YAML: {e}")
        return {}


def save_yaml_to_file(structured_data, output_path):
    """
    Save structured YAML data to a file.
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as file:
            yaml.dump(structured_data, file, allow_unicode=True, sort_keys=False, indent=4)
        print(f"Structured YAML saved to {output_path}")
    except Exception as e:
        print(f"Error saving structured YAML to file: {e}")


# Example usage
if __name__ == "__main__":
    file_path = r"CPQ_Ausschreibung1.pdf"

    # Convert PDF to vector store
    db = convert_to_vector_store(file_path)
    save_path = "store/vectorstore"
    save_vector_store(db, save_path)

    # Load the vector store
    # Updated embedding model to multilingual (if available)
    embedding = CohereEmbeddings(model="embed-multilingual-v2.0")  # Use appropriate model for German
    db = load_vector_store(save_path, embedding)

    # Query the vector store with a German query
    # query1 = "Was sind wichtige Punkte in der Ausschreibung?"
    # query2 = "Liste die Kontaktinformationen, einschließlich Name, E-Mail, und Rolle, sowie die Projektphasen mit Zeitangaben."
    query = "What are important things in the tender?"
    results = query_vector_store(db, query, top_k=5)

    # Combine retrieved texts
    retrieved_text = "\n".join([doc.page_content for doc in results])

    # Generate structured YAML
    structured_data = generate_structured_yaml(retrieved_text)

    # Print and save the structured YAML
    if structured_data:
        print(yaml.dump(structured_data, sort_keys=False, indent=4, allow_unicode=True))

        # Save the structured YAML to a file
        output_yaml_path = "output/structured_tender.yaml"
        save_yaml_to_file(structured_data, output_yaml_path)
    else:
        print("Failed to generate structured YAML.")