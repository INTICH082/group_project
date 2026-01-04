#pragma once

#include <mongocxx/client.hpp>
#include <mongocxx/instance.hpp>
#include <mongocxx/database.hpp>
#include <mongocxx/collection.hpp>
#include <mongocxx/options/update.hpp>  // для upsert
#include <nlohmann/json.hpp>
#include <string>

using namespace std;
using json = nlohmann::json;

extern mongocxx::instance inst;
extern mongocxx::client conn;
extern mongocxx::database db;
extern mongocxx::collection login_states;

void save_login_state(const string& token, const json& data, int ttl_seconds = 600);

json get_login_state(const string& token);

void init_mongo_ttl();