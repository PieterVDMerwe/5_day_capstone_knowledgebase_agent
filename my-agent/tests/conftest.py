import os
import sys
import shutil
import pytest
from unittest.mock import patch, MagicMock

# Force python to find the app module correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Define test-specific paths inside a temp directory in the test folder
TEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_run_env"))
TEST_DB_PATH = os.path.join(TEST_DIR, "lore_vault_test.db")
TEST_VAULT_DIR = os.path.join(TEST_DIR, "ObsidianTest")

# Re-configure the app paths
import app.database
import app.file_writer

app.database.DB_PATH = TEST_DB_PATH
app.file_writer.VAULT_DIR = TEST_VAULT_DIR

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    # Setup test directory
    os.makedirs(TEST_DIR, exist_ok=True)
    os.makedirs(TEST_VAULT_DIR, exist_ok=True)
    
    yield
    
    # Teardown
    if os.path.exists(TEST_DIR):
        try:
            shutil.rmtree(TEST_DIR)
        except Exception as e:
            print(f"Failed to clear test env folder: {e}")

@pytest.fixture(autouse=True)
def clean_db_and_vault():
    # Initialize DB if not exists
    from app.database import init_db, get_db_connection
    init_db()
    
    # Clear all tables to ensure test isolation (avoids locked file errors on Windows)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM entities")
        cursor.execute("DELETE FROM edges")
        cursor.execute("DELETE FROM name_index")
        cursor.execute("DELETE FROM memberships")
        cursor.execute("DELETE FROM containment")
        cursor.execute("DELETE FROM genealogy")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to clear DB tables: {e}")
    
    # Clean vault files
    if os.path.exists(TEST_VAULT_DIR):
        for f in os.listdir(TEST_VAULT_DIR):
            fp = os.path.join(TEST_VAULT_DIR, f)
            if os.path.isfile(fp):
                os.remove(fp)
            elif os.path.isdir(fp):
                shutil.rmtree(fp)
    else:
        os.makedirs(TEST_VAULT_DIR, exist_ok=True)
    
    yield

@pytest.fixture
def mock_llm_client():
    with patch('app.llm_client.LLMClient.generate') as mock_gen:
        yield mock_gen
