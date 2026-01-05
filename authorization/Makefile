CXX = g++
CXXFLAGS = -std=c++11 -Wall -O2
LIBS = -lmysqlclient -lssl -lcrypto -lpthread

SRC = main.cpp server.cpp auth.cpp database.cpp utils.cpp
OBJ = $(SRC:.cpp=.o)
EXE = auth_server

all: $(EXE)

$(EXE): $(OBJ)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LIBS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(OBJ) $(EXE)

run: $(EXE)
	./$(EXE)