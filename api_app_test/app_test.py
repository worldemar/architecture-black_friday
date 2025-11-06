import time

import requests


def _http_get(url: str):
    return requests.get(url, timeout=5)

API_BASE_URL = "http://pymongo_api:8080"
COLLECTION_NAME = "helloDoc"
EXPECTED_MIN_DOCUMENTS = 1000


class TestAPIAvailability:
    """Test that API is accessible from web"""

    def test_api_is_reachable(self):
        """Verify that API responds to HTTP requests"""
        response = _http_get(f"{API_BASE_URL}/")
        assert response.status_code == 200, f"API not reachable, status code: {response.status_code}"

    def test_api_returns_json(self):
        """Verify that API returns valid JSON"""
        response = _http_get(f"{API_BASE_URL}/")
        assert response.headers.get("content-type") == "application/json", "Response is not JSON"
        data = response.json()
        assert isinstance(data, dict), "Response is not a JSON object"


class TestRootEndpoint:
    """Test root endpoint"""

    def test_root_endpoint_status(self):
        """Verify root endpoint returns status OK"""
        response = _http_get(f"{API_BASE_URL}/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "OK", "Status is not OK"

    def test_root_endpoint_has_mongodb_info(self):
        """Verify root endpoint returns MongoDB information"""
        response = _http_get(f"{API_BASE_URL}/")
        data = response.json()

        # Check for essential MongoDB info fields
        assert "mongo_topology_type" in data, "Missing mongo_topology_type"
        assert "mongo_db" in data, "Missing mongo_db"
        assert "collections" in data, "Missing collections"
        assert "status" in data, "Missing status"

    def test_root_endpoint_has_collections_info(self):
        """Verify root endpoint returns collections information"""
        response = _http_get(f"{API_BASE_URL}/")
        data = response.json()

        collections = data.get("collections", {})
        assert isinstance(collections, dict), "Collections should be a dictionary"

        # Verify helloDoc collection exists and has document count
        if COLLECTION_NAME in collections:
            assert "documents_count" in collections[COLLECTION_NAME], \
                f"Collection {COLLECTION_NAME} missing documents_count"

    def test_root_endpoint_has_cache_info(self):
        """Verify root endpoint returns cache information"""
        response = _http_get(f"{API_BASE_URL}/")
        data = response.json()

        assert "cache_enabled" in data, "Missing cache_enabled field"
        assert isinstance(data["cache_enabled"], bool), "cache_enabled should be boolean"


class TestMongoDBData:
    """Test MongoDB data as per requirements (≥1000 documents)"""

    def test_database_has_minimum_documents(self):
        """Verify database has at least 1000 documents as per task requirements"""
        response = _http_get(f"{API_BASE_URL}/")
        data = response.json()

        collections = data.get("collections", {})
        assert COLLECTION_NAME in collections, f"Collection {COLLECTION_NAME} not found"

        doc_count = collections[COLLECTION_NAME].get("documents_count", 0)
        assert doc_count >= EXPECTED_MIN_DOCUMENTS, \
            f"Expected at least {EXPECTED_MIN_DOCUMENTS} documents, got {doc_count}"

    def test_count_endpoint(self):
        """Verify /{collection_name}/count endpoint works"""
        response = _http_get(f"{API_BASE_URL}/{COLLECTION_NAME}/count")
        assert response.status_code == 200

        data = response.json()
        assert data.get("status") == "OK", "Status is not OK"
        assert "items_count" in data, "Missing items_count"
        assert data["items_count"] >= EXPECTED_MIN_DOCUMENTS, \
            f"Expected at least {EXPECTED_MIN_DOCUMENTS} items"


class TestUsersEndpoints:
    """Test user-related endpoints"""

    def test_list_users_endpoint(self):
        """Verify /{collection_name}/users endpoint returns user list"""
        response = _http_get(f"{API_BASE_URL}/{COLLECTION_NAME}/users")
        assert response.status_code == 200

        data = response.json()
        assert "users" in data, "Missing users field"
        assert isinstance(data["users"], list), "Users should be a list"
        assert len(data["users"]) > 0, "Users list is empty"

    def test_users_have_correct_structure(self):
        """Verify user objects have expected fields"""
        response = _http_get(f"{API_BASE_URL}/{COLLECTION_NAME}/users")
        data = response.json()

        users = data.get("users", [])
        assert len(users) > 0, "No users to verify"

        # Check first user has required fields
        first_user = users[0]
        assert "name" in first_user, "User missing name field"
        assert "age" in first_user, "User missing age field"

    def test_get_specific_user(self):
        """Verify /{collection_name}/users/{name} endpoint works"""
        # First get a user from the list
        response = _http_get(f"{API_BASE_URL}/{COLLECTION_NAME}/users")
        data = response.json()
        users = data.get("users", [])

        if len(users) > 0:
            user_name = users[0]["name"]

            # Get specific user
            response = _http_get(f"{API_BASE_URL}/{COLLECTION_NAME}/users/{user_name}")
            assert response.status_code == 200

            user_data = response.json()
            assert user_data["name"] == user_name, "Retrieved wrong user"

    def test_get_nonexistent_user_returns_404(self):
        """Verify getting non-existent user returns 404"""
        response = _http_get(f"{API_BASE_URL}/{COLLECTION_NAME}/users/nonexistent_user_12345")
        assert response.status_code == 404, "Expected 404 for non-existent user"


class TestAPIDocumentation:
    """Test API documentation endpoint"""

    def test_docs_endpoint_exists(self):
        """Verify /docs endpoint is available (Swagger)"""
        response = _http_get(f"{API_BASE_URL}/docs")
        assert response.status_code == 200, "API documentation not available"


class TestAPIHealth:
    """Test overall API health and responsiveness"""

    def test_api_responds_quickly(self):
        """Verify API responds within reasonable time"""
        start_time = time.time()
        response = _http_get(f"{API_BASE_URL}/")
        elapsed_time = time.time() - start_time

        assert response.status_code == 200
        assert elapsed_time < 1.0, f"API response too slow: {elapsed_time:.2f}s"

    def test_multiple_requests_work(self):
        """Verify API can handle multiple sequential requests"""
        for _ in range(5):
            response = _http_get(f"{API_BASE_URL}/")
            assert response.status_code == 200, "API failed on repeated requests"
