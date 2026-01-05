#pragma once
#include <string>
#include <cstdlib>

using namespace std;

struct Config {
    string mysql_host     = "127.0.0.1";
    string mysql_user     = "root";
    string mysql_password = "test01";  
    string mysql_db       = "Project";
    unsigned int mysql_port    = 3306;
    int server_port            = 18080;
};

extern Config cfg;