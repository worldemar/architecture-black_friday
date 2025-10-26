#!/bin/bash

COLOR_RED='\033[0;31m'
COLOR_CYAN='\033[0;36m'
COLOR_YELLOW='\033[0;33m'
COLOR_GREEN='\033[0;32m'
COLOR_RESET='\033[0m'

function log_info () {
    echo -e "[${COLOR_CYAN}INFO${COLOR_RESET}] $1"
}

function log_fail () {
    echo -e "[${COLOR_RED}FAIL${COLOR_RESET}] $1"
    exit 1
}

function log_warn () {
    echo -e "[${COLOR_YELLOW}WARN${COLOR_RESET}] $1"
}

function log_ok () {
    echo -e "[ ${COLOR_GREEN}OK${COLOR_RESET} ] $1"
}

function wait_for_healthy () {
    local container_name="$1"
    local timeout="${2:-180}"

    log_info "Waiting for container ${container_name} to become healthy"

    local start_time
    start_time=$(date +%s)

    while true; do
        local status
        status=$(docker compose ps "${container_name}" | tail -n +2)

        if echo "${status}" | grep -q "(healthy)"; then
            log_ok "Container ${container_name} is healthy"
            break
        fi

        local now
        now=$(date +%s)
        if (( now - start_time >= timeout )); then
            echo "${status}"
            log_fail "Container ${container_name} did not become healthy within ${timeout} seconds"
        fi

        sleep 3
    done
}

set -e

log_info "[1/14] Initializing Config Server Replica Set with 3 members"
wait_for_healthy "configSrv"
wait_for_healthy "configSrv2"
wait_for_healthy "configSrv3"
docker compose exec -T configSrv mongosh --port 27017 --quiet <<EOF > /dev/null 2>&1 || true
rs.initiate({
  _id: "config_server",
  configsvr: true,
  members: [
    { _id: 0, host: "configSrv:27017" },
    { _id: 1, host: "configSrv2:27017" },
    { _id: 2, host: "configSrv3:27017" }
  ]
});
EOF
log_info "Checking Config Server replica set status"
_config_status=$(docker compose exec -T configSrv mongosh --port 27017 --quiet <<EOF 2>&1
rs.status().ok
EOF
)
_config_status_ok=$(echo "${_config_status}" | sed 's/.*> *//' | tr -d ' \r\n')
if [[ ${_config_status_ok} -ne 1 ]]; then
    echo "${_config_status}"
    log_fail "Config Server replica set status is not OK. See status above."
else
    log_ok "Config Server replica set initialized with 3 members and ready"
fi



log_info "[2/14] Initializing Shard 1 Replica Set with 3 members"
wait_for_healthy "shard1-1"
wait_for_healthy "shard1-2"
wait_for_healthy "shard1-3"
docker compose exec -T shard1-1 mongosh --port 27018 --quiet <<EOF > /dev/null 2>&1 || true
rs.initiate({
  _id: "shard1",
  members: [
    { _id: 0, host: "shard1-1:27018" },
    { _id: 1, host: "shard1-2:27018" },
    { _id: 2, host: "shard1-3:27018" }
  ]
});
EOF
log_info "Checking Shard 1 replica set status"
_shard1_status=$(docker compose exec -T shard1-1 mongosh --port 27018 --quiet <<EOF 2>&1
rs.status().ok
EOF
)
_shard1_status_ok=$(echo "${_shard1_status}" | sed 's/.*> *//' | tr -d ' \r\n')
if [[ ${_shard1_status_ok} -ne 1 ]]; then
    echo "${_shard1_status}"
    log_fail "Shard 1 replica set status is not OK. See status above."
else
    log_ok "Shard 1 replica set initialized with 3 members and ready"
fi



log_info "[3/14] Initializing Shard 2 Replica Set with 3 members"
wait_for_healthy "shard2-1"
wait_for_healthy "shard2-2"
wait_for_healthy "shard2-3"
docker compose exec -T shard2-1 mongosh --port 27019 --quiet <<EOF > /dev/null 2>&1 || true
rs.initiate({
  _id: "shard2",
  members: [
    { _id: 0, host: "shard2-1:27019" },
    { _id: 1, host: "shard2-2:27019" },
    { _id: 2, host: "shard2-3:27019" }
  ]
});
EOF
log_info "Waiting for Shard 2 replica set to elect primary"
log_info "Checking Shard 2 replica set status"
_shard2_status=$(docker compose exec -T shard2-1 mongosh --port 27019 --quiet <<EOF 2>&1
rs.status().ok
EOF
)
_shard2_status_ok=$(echo "${_shard2_status}" | sed 's/.*> *//' | tr -d ' \r\n')
if [[ ${_shard2_status_ok} -ne 1 ]]; then
    echo "${_shard2_status}"
    log_fail "Shard 2 replica set status is not OK. See status above."
else
    log_ok "Shard 2 replica set initialized with 3 members and ready"
fi



log_info "[4/14] Adding Shard 1 to cluster"
log_info "Waiting for mongos router to be ready (10s)"
sleep 10
wait_for_healthy "mongos_router"
_shard1_add_result=$(docker compose exec -T mongos_router mongosh --port 27020 --quiet --eval 'sh.addShard("shard1/shard1-1:27018,shard1-2:27018,shard1-3:27018")' 2>&1)
log_info "Checking if Shard 1 was added to cluster"
_shard1_in_cluster=$(docker compose exec -T mongos_router mongosh --port 27020 --quiet <<EOF 2>&1
db.adminCommand({ listShards: 1 })
EOF
)
_shard1_found=$(echo "${_shard1_in_cluster}" | grep -o "shard1" | wc -l)
if [[ ${_shard1_found} -lt 1 ]]; then
    echo "${_shard1_add_result}"
    echo "${_shard1_in_cluster}"
    log_fail "Shard 1 not found in cluster. See cluster status above."
else
    log_ok "Shard 1 (with 3 replicas) added to cluster"
fi



log_info "[5/14] Adding Shard 2 to cluster"
wait_for_healthy "mongos_router"
_shard2_add_result=$(docker compose exec -T mongos_router mongosh --port 27020 --quiet --eval 'sh.addShard("shard2/shard2-1:27019,shard2-2:27019,shard2-3:27019")' 2>&1)
log_info "Checking if Shard 2 was added to cluster"
_shard2_in_cluster=$(docker compose exec -T mongos_router mongosh --port 27020 --quiet <<EOF 2>&1
db.adminCommand({ listShards: 1 })
EOF
)
_shard2_found=$(echo "${_shard2_in_cluster}" | grep -o "shard2" | wc -l)
if [[ ${_shard2_found} -lt 1 ]]; then
    echo "${_shard2_add_result}"
    echo "${_shard2_in_cluster}"
    log_fail "Shard 2 not found in cluster. See cluster status above."
else
    log_ok "Shard 2 (with 3 replicas) added to cluster"
fi



log_info "[6/14] Enabling sharding for database 'somedb' and collection 'helloDoc'"
wait_for_healthy "mongos_router"
_enable_sharding_result=$(docker compose exec -T mongos_router mongosh --port 27020 --quiet <<EOF 2>&1
sh.enableSharding("somedb");
sh.shardCollection("somedb.helloDoc", { "name": "hashed" });
EOF
)
log_info "Checking if sharding is enabled for collection"
_collection_sharded=$(docker compose exec -T mongos_router mongosh --port 27020 --quiet <<EOF 2>&1
use somedb
db.helloDoc.getShardDistribution()
EOF
)
_shard_key_found=$(echo "${_collection_sharded}" | grep -o "Shard" | wc -l)
if [[ ${_shard_key_found} -lt 2 ]]; then
    echo "${_enable_sharding_result}"
    echo "${_collection_sharded}"
    log_fail "Collection 'somedb.helloDoc' is not sharded properly. See distribution above."
else
    log_ok "Sharding enabled for somedb.helloDoc"
fi



log_info "[7/14] Populating collection with 1000 documents"
wait_for_healthy "mongos_router"
docker compose exec -T mongos_router mongosh --port 27020 --quiet <<EOF > /dev/null 2>&1
use somedb
for(var i = 0; i < 1000; i++) {
  db.helloDoc.insert({age: 18 + i % 80, name: "name" + i});
}
EOF
log_info "Checking if documents were inserted"
_total_docs_str=$(docker compose exec -T mongos_router mongosh --port 27020 --quiet <<EOF 2>&1
use somedb
db.helloDoc.countDocuments();
EOF
)
_total_docs=$(echo "${_total_docs_str}" | sed 's/.*> *//' | grep -E '^[0-9]+$' | tail -1 | tr -d ' \r\n')
_expected_docs=1000
# Check if we have at least the expected number (for repeat starts, doc count will be multiple of 1000)
if [[ -z ${_total_docs} || ${_total_docs} -lt ${_expected_docs} ]]; then
    echo "${_total_docs_str}"
    log_fail "Expected at least ${_expected_docs} documents, but found ${_total_docs}. See output above."
else
    log_ok "Collection has ${_total_docs} documents (expected at least ${_expected_docs})"
fi



log_info "[8/14] Checking if mongos router reports sharding metadata"
wait_for_healthy "mongos_router"
_sharding_status=$(docker compose exec -T mongos_router mongosh --port 27020 --quiet <<EOF 2>&1
sh.status()
EOF
)
_sharding_items=(
  "^shards$"
  "^active.mongoses$"
  "^balancer$"
  "^shardedDataDistribution$"
  "^databases$"
)
for _sharding_item in "${_sharding_items[@]}"
do
  _sharding_status_have_shards=$(echo "${_sharding_status}" | grep -oE ${_sharding_item} | wc -l)
  if [[ ${_sharding_status_have_shards} -ne 1 ]]; then
      echo "${_sharding_status}"
      log_fail "Sharding is not reporting ${_sharding_item}. See status above."
  else
      log_ok "Sharding is reporting ${_sharding_item}"
  fi
done



_shard_docs_expected=300

log_info "[9/14] Checking documents in Shard 1 (primary replica)"
wait_for_healthy "shard1-1"
_shard1_docs_str=$(docker compose exec -T shard1-1 mongosh --port 27018 --quiet <<EOF 2>&1
use somedb
db.helloDoc.countDocuments();
EOF
)
_shard1_docs=$(echo "${_shard1_docs_str}" | sed 's/.*> *//' | grep -E '^[0-9]+$' | tail -1 | tr -d ' \r\n')
if [[ -z ${_shard1_docs} || ${_shard1_docs} -lt ${_shard_docs_expected} ]]; then
    echo "${_shard1_docs_str}"
    log_fail "Shard 1 has ${_shard1_docs} documents, but expected at least ${_shard_docs_expected}. See Shard 1 status above."
else
    log_ok "Shard 1 has ${_shard1_docs} documents (expected at least ${_shard_docs_expected})"
fi

log_info "[10/14] Checking documents in Shard 2 (primary replica)"
wait_for_healthy "shard2-1"
_shard2_docs_str=$(docker compose exec -T shard2-1 mongosh --port 27019 --quiet <<EOF 2>&1
use somedb
db.helloDoc.countDocuments();
EOF
)
_shard2_docs=$(echo "${_shard2_docs_str}" | sed 's/.*> *//' | grep -E '^[0-9]+$' | tail -1 | tr -d ' \r\n')
if [[ -z ${_shard2_docs} || ${_shard2_docs} -lt ${_shard_docs_expected} ]]; then
    echo "${_shard2_docs_str}"
    log_fail "Shard 2 has ${_shard2_docs} documents, but expected at least ${_shard_docs_expected}. See Shard 2 status above."
else
    log_ok "Shard 2 has ${_shard2_docs} documents (expected at least ${_shard_docs_expected})"
fi



log_info "[11/14] Verifying replication for Config Server"
wait_for_healthy "configSrv"
_config_members=$(docker compose exec -T configSrv mongosh --port 27017 --quiet <<EOF 2>&1
rs.status().members.length
EOF
)
_config_members_count=$(echo "${_config_members}" | sed 's/.*> *//' | tr -d ' \r\n')
if [[ ${_config_members_count} -ne 3 ]]; then
    echo "${_config_members}"
    log_fail "Config Server should have 3 replica members, but found ${_config_members_count}."
else
    log_ok "Config Server has 3 replica members"
fi

log_info "[12/14] Verifying replication for Shard 1"
wait_for_healthy "shard1-1"
_shard1_members=$(docker compose exec -T shard1-1 mongosh --port 27018 --quiet <<EOF 2>&1
rs.status().members.length
EOF
)
_shard1_members_count=$(echo "${_shard1_members}" | sed 's/.*> *//' | tr -d ' \r\n')
if [[ ${_shard1_members_count} -ne 3 ]]; then
    echo "${_shard1_members}"
    log_fail "Shard 1 should have 3 replica members, but found ${_shard1_members_count}."
else
    log_ok "Shard 1 has 3 replica members"
fi

log_info "[13/14] Verifying replication for Shard 2"
wait_for_healthy "shard2-1"
_shard2_members=$(docker compose exec -T shard2-1 mongosh --port 27019 --quiet <<EOF 2>&1
rs.status().members.length
EOF
)
_shard2_members_count=$(echo "${_shard2_members}" | sed 's/.*> *//' | tr -d ' \r\n')
if [[ ${_shard2_members_count} -ne 3 ]]; then
    echo "${_shard2_members}"
    log_fail "Shard 2 should have 3 replica members, but found ${_shard2_members_count}."
else
    log_ok "Shard 2 has 3 replica members"
fi



log_info "[14/14] Verifying that all containers are now healthy"
_all_containers=$(docker compose ps)
_all_healthy_count=$(echo "${_all_containers}" | grep -o "(healthy)" | wc -l)
_all_containers_expected=12
if [[ ${_all_healthy_count} -ne ${_all_containers_expected} ]]; then
    echo "${_all_containers}"
    log_fail "Expected all ${_all_containers_expected} containers to be healthy after initialization, but found ${_all_healthy_count}"
else
    log_ok "All ${_all_containers_expected} containers are healthy!"
fi



log_info "You can now access the application at: http://localhost:8080"
log_info "API documentation available at: http://localhost:8080/docs"
