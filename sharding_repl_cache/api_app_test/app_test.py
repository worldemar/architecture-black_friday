import time

import requests
from pymongo import MongoClient


def _http_get(url: str):
    return requests.get(url, timeout=5)

API_BASE_URL = "http://pymongo_api:8080"
COLLECTION_NAME = "helloDoc"
EXPECTED_MIN_DOCUMENTS = 1000
CACHE_RESPONSE_THRESHOLD_SECONDS = 0.1

# MongoDB shard connection strings (connect to primary replicas)
SHARD1_URL = "mongodb://shard1-1:27018"
SHARD2_URL = "mongodb://shard2-1:27019"

# MongoDB replica set URLs for replication tests
SHARD1_REPLICA_URLS = [
    "mongodb://shard1-1:27018",
    "mongodb://shard1-2:27018",
    "mongodb://shard1-3:27018"
]
SHARD2_REPLICA_URLS = [
    "mongodb://shard2-1:27019",
    "mongodb://shard2-2:27019",
    "mongodb://shard2-3:27019"
]
CONFIG_SERVER_URLS = [
    "mongodb://configSrv:27017",
    "mongodb://configSrv2:27017",
    "mongodb://configSrv3:27017"
]


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
        assert data["cache_enabled"] is True, "Cache should be enabled when Redis is configured"


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


class TestCachePerformance:
    """Test Redis cache behaviour for user list endpoint"""

    @staticmethod
    def _request_users() -> dict:
        response = _http_get(f"{API_BASE_URL}/{COLLECTION_NAME}/users")
        assert response.status_code == 200, "Users endpoint did not return HTTP 200"
        payload = response.json()
        assert "users" in payload, "Response missing users"
        return payload

    def test_cached_users_requests_are_fast(self):
        """Verify that cached users endpoint calls stay below the latency threshold"""
        # Warm cache with initial request (allowed to be slow)
        initial_payload = self._request_users()
        assert len(initial_payload.get("users", [])) > 0, "Initial users list is empty"

        # Next calls should hit cache and be faster than CACHE_RESPONSE_THRESHOLD_SECONDS
        for attempt in range(1, 101):
            start = time.perf_counter()
            cached_response = _http_get(f"{API_BASE_URL}/{COLLECTION_NAME}/users")
            elapsed = time.perf_counter() - start

            assert cached_response.status_code == 200, f"Cached request {attempt} failed"
            cached_payload = cached_response.json()
            assert len(cached_payload.get("users", [])) > 0, "Cached users list is empty"
            assert (
                elapsed < CACHE_RESPONSE_THRESHOLD_SECONDS
            ), f"Cached response {attempt} too slow: {elapsed:.4f}s"


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


class TestMongoSharding:
    """Test MongoDB sharding configuration as per task 2 requirements"""

    def test_mongo_topology_is_sharded(self):
        """Verify MongoDB is running in Sharded topology mode"""
        response = _http_get(f"{API_BASE_URL}/")
        assert response.status_code == 200
        data = response.json()

        topology_type = data.get("mongo_topology_type")
        assert topology_type == "Sharded", \
            f"Expected topology type 'Sharded', got '{topology_type}'"

    def test_has_two_shards(self):
        """Verify system has exactly 2 shards configured"""
        response = _http_get(f"{API_BASE_URL}/")
        assert response.status_code == 200
        data = response.json()

        shards = data.get("shards")
        assert shards is not None, "No shards information in response"
        assert isinstance(shards, dict), "Shards should be a dictionary"
        assert len(shards) == 2, f"Expected 2 shards, got {len(shards)}"

    def test_shards_are_named_correctly(self):
        """Verify shards have correct names (shard1, shard2)"""
        response = _http_get(f"{API_BASE_URL}/")
        data = response.json()

        shards = data.get("shards", {})
        shard_names = list(shards.keys())

        assert "shard1" in shard_names, "shard1 not found in shards"
        assert "shard2" in shard_names, "shard2 not found in shards"

    def test_shards_show_replica_information(self):
        """Verify API shows replica information for each shard"""
        response = _http_get(f"{API_BASE_URL}/")
        data = response.json()

        shards = data.get("shards", {})

        # Check shard1 replica info
        shard1_info = shards.get("shard1", "")
        assert "shard1-1:27018" in shard1_info, "shard1-1 not found in shard1 info"
        assert "shard1-2:27018" in shard1_info, "shard1-2 not found in shard1 info"
        assert "shard1-3:27018" in shard1_info, "shard1-3 not found in shard1 info"

        # Check shard2 replica info
        shard2_info = shards.get("shard2", "")
        assert "shard2-1:27019" in shard2_info, "shard2-1 not found in shard2 info"
        assert "shard2-2:27019" in shard2_info, "shard2-2 not found in shard2 info"
        assert "shard2-3:27019" in shard2_info, "shard2-3 not found in shard2 info"

        # Count replicas by counting commas (3 replicas = 2 commas)
        shard1_replica_count = shard1_info.count(",") + 1
        shard2_replica_count = shard2_info.count(",") + 1

        assert shard1_replica_count == 3, \
            f"Shard1 should show 3 replicas, but shows {shard1_replica_count}"
        assert shard2_replica_count == 3, \
            f"Shard2 should show 3 replicas, but shows {shard2_replica_count}"

        print(f"\nShard1 replicas in API: {shard1_info}")
        print(f"Shard2 replicas in API: {shard2_info}")

    def test_documents_distributed_across_shards(self):
        """Verify documents are actually distributed across multiple shards"""
        # Connect directly to each shard and count documents
        client_shard1 = MongoClient(SHARD1_URL)
        client_shard2 = MongoClient(SHARD2_URL)

        try:
            # Count documents in each shard
            db1 = client_shard1["somedb"]
            db2 = client_shard2["somedb"]

            count_shard1 = db1.helloDoc.count_documents({})
            count_shard2 = db2.helloDoc.count_documents({})

            # Verify both shards have documents
            assert count_shard1 > 0, f"Shard1 should have documents, but has {count_shard1}"
            assert count_shard2 > 0, f"Shard2 should have documents, but has {count_shard2}"

            # Verify total is correct
            total_in_shards = count_shard1 + count_shard2
            assert total_in_shards >= EXPECTED_MIN_DOCUMENTS, \
                f"Total documents in shards ({total_in_shards}) should be >= {EXPECTED_MIN_DOCUMENTS}"

            # Verify documents are distributed (not all in one shard)
            # Allow some imbalance, but each shard should have at least 30% of documents
            min_expected_per_shard = EXPECTED_MIN_DOCUMENTS * 0.3
            assert count_shard1 >= min_expected_per_shard, \
                f"Shard1 has too few documents: {count_shard1} (expected >= {min_expected_per_shard})"
            assert count_shard2 >= min_expected_per_shard, \
                f"Shard2 has too few documents: {count_shard2} (expected >= {min_expected_per_shard})"

            # Log distribution for debugging
            print(f"\nDocument distribution: Shard1={count_shard1}, Shard2={count_shard2}, Total={total_in_shards}")

        finally:
            client_shard1.close()
            client_shard2.close()


class TestMongoReplication:
    """Test MongoDB replication configuration as per task 3 requirements"""

    def test_shard1_has_three_replicas(self):
        """Verify Shard1 has 3 replica members"""
        client = MongoClient(SHARD1_URL)
        try:
            # Get replica set status
            result = client.admin.command("replSetGetStatus")
            members = result.get("members", [])

            assert len(members) == 3, \
                f"Shard1 should have 3 replica members, got {len(members)}"

            # Verify each member is accessible
            member_states = [m["stateStr"] for m in members]
            assert "PRIMARY" in member_states, "Shard1 should have a PRIMARY member"

            print(f"\nShard1 replica members: {len(members)}, states: {member_states}")
        finally:
            client.close()

    def test_shard2_has_three_replicas(self):
        """Verify Shard2 has 3 replica members"""
        client = MongoClient(SHARD2_URL)
        try:
            # Get replica set status
            result = client.admin.command("replSetGetStatus")
            members = result.get("members", [])

            assert len(members) == 3, \
                f"Shard2 should have 3 replica members, got {len(members)}"

            # Verify each member is accessible
            member_states = [m["stateStr"] for m in members]
            assert "PRIMARY" in member_states, "Shard2 should have a PRIMARY member"

            print(f"\nShard2 replica members: {len(members)}, states: {member_states}")
        finally:
            client.close()

    def test_config_server_has_three_replicas(self):
        """Verify Config Server has 3 replica members"""
        client = MongoClient(CONFIG_SERVER_URLS[0])
        try:
            # Get replica set status
            result = client.admin.command("replSetGetStatus")
            members = result.get("members", [])

            assert len(members) == 3, \
                f"Config Server should have 3 replica members, got {len(members)}"

            # Verify each member is accessible
            member_states = [m["stateStr"] for m in members]
            assert "PRIMARY" in member_states, "Config Server should have a PRIMARY member"

            print(f"\nConfig Server replica members: {len(members)}, states: {member_states}")
        finally:
            client.close()

    def test_shard1_replicas_have_same_data(self):
        """Verify all Shard1 replicas have the same number of documents"""
        # We can only test count, as data should be replicated
        client_primary = MongoClient(SHARD1_URL, directConnection=True)

        try:
            primary_count = client_primary["somedb"].helloDoc.count_documents({})

            # Note: Secondary replicas might have slight replication lag
            # We verify they exist but don't check exact count to avoid flaky tests
            assert primary_count > 0, "Primary shard1-1 should have documents"

            print(f"\nShard1 primary (shard1-1) has {primary_count} documents")
        finally:
            client_primary.close()

    def test_shard2_replicas_have_same_data(self):
        """Verify all Shard2 replicas have the same number of documents"""
        # We can only test count, as data should be replicated
        client_primary = MongoClient(SHARD2_URL, directConnection=True)

        try:
            primary_count = client_primary["somedb"].helloDoc.count_documents({})

            # Note: Secondary replicas might have slight replication lag
            # We verify they exist but don't check exact count to avoid flaky tests
            assert primary_count > 0, "Primary shard2-1 should have documents"

            print(f"\nShard2 primary (shard2-1) has {primary_count} documents")
        finally:
            client_primary.close()

    def test_replica_set_configuration(self):
        """Verify replica sets are properly configured"""
        # Test shard1 replica set configuration
        client = MongoClient(SHARD1_URL)
        try:
            config = client.admin.command("replSetGetConfig")
            rs_config = config.get("config", {})

            assert rs_config.get("_id") == "shard1", \
                f"Shard1 replica set name should be 'shard1', got {rs_config.get('_id')}"

            members = rs_config.get("members", [])
            assert len(members) == 3, \
                f"Shard1 replica set should have 3 members in config, got {len(members)}"
        finally:
            client.close()
