#include "mongo.hpp"
#include "config.hpp"
#include <bsoncxx/builder/stream/document.hpp>
#include <bsoncxx/json.hpp>
#include <bsoncxx/types.hpp>
#include <mongocxx>

using bsoncxx::builder::stream::document;
using bsoncxx::builder::stream::open_document;
using bsoncxx::builder::stream::close_document;
using bsoncxx::builder::stream::finalize;

mongocxx::instance inst{};
mongocxx::client conn{mongocxx::uri{cfg.mongo_uri}};
mongocxx::database db = conn[cfg.db_name];
mongocxx::collection login_states = db["login_states"];

void init_mongo_ttl() {
    try {
        bsoncxx::document::value key = document{} << "expires" << 1 << finalize;
        mongocxx::options::index index_opts{};
        index_opts.expire_after_seconds(0);  // TTL = 0 → удалять по значению поля expires

        login_states.create_index(key.view(), index_opts);
    } catch (const mongocxx::exception& e) {
        // Индекс уже существует или другая ошибка — игнорируем
        if (e.code().value() != 85 && e.code().value() != 68) {  // 85 = IndexOptionsConflict, 68 = AlreadyExists
            throw;
        }
    }
}

void save_login_state(const string& token, const json& data, int ttl_seconds) {
    auto filter = document{} << "token" << token << finalize;

    auto now = std::chrono::system_clock::now();
    auto expires = now + std::chrono::seconds(ttl_seconds);

    auto update = document{} << "$set" << open_document
                             << "data" << bsoncxx::from_json(data.dump())
                             << "expires" << bsoncxx::types::b_date{expires}
                             << close_document
                             << "$setOnInsert" << open_document  // если upsert, то можно добавить другие поля
                             << close_document
                             << finalize;

    mongocxx::options::update opts{};
    opts.upsert(true);

    login_states.update_one(filter.view(), update.view(), opts);
}

json get_login_state(const string& token) {
    auto filter = document{} << "token" << token << finalize;

    auto opts = mongocxx::options::find_one{};
    auto doc = login_states.find_one(filter.view(), opts);

    if (!doc) {
        return json{};
    }

    auto view = doc->view();
    auto expires_opt = view["expires"].get_date();

    if (expires_opt.value < std::chrono::system_clock::now()) {
        login_states.delete_one(filter.view());
        return json{};
    }

    auto data_bson = view["data"].get_document().value;
    return json::parse(bsoncxx::to_json(data_bson));
}