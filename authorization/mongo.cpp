#include "mongo_utils.hpp"
#include "config.hpp"
#include <bsoncxx/builder/stream/document.hpp>
#include <bsoncxx/json.hpp>

mongocxx::instance inst{};
mongocxx::client conn{mongocxx::uri{cfg.mongo_uri}};
mongocxx::database db = conn[cfg.db_name];
mongocxx::collection login_states = db["login_states"];

void save_login_state(const string& token, const json& data, int ttl_seconds) {
    using bsoncxx::builder::stream::document;

    auto filter = document{} << "token" << token << bsoncxx::builder::stream::finalize;
    auto update = document{}
        << "$set" << bsoncxx::builder::stream::open_document
           << "data" << bsoncxx::from_json(data.dump())
           << "expires" << bsoncxx::types::b_date{chrono::system_clock::now() + chrono::seconds(ttl_seconds)}
        << bsoncxx::builder::stream::close_document
        << bsoncxx::builder::stream::finalize;

    login_states.update_one(filter.view(), update.view(), mongocxx::options::update{}.upsert(true));
}

json get_login_state(const string& token) {
    using bsoncxx::builder::stream::document;

    auto filter = document{} << "token" << token << bsoncxx::builder::stream::finalize;
    auto maybe_doc = login_states.find_one(filter.view());

    if (!maybe_doc) return nullptr;

    auto view = maybe_doc->view();
    if (view["expires"].get_date().value < chrono::system_clock::now()) {
        login_states.delete_one(filter.view());
        return nullptr;
    }

    return json::parse(bsoncxx::to_json(view["data"].get_document().value));
}