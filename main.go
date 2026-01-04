package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
)

func main() {
	InitDB() // Должна быть в database.go

	mux := http.NewServeMux()

	// Маршруты
	mux.HandleFunc("/questions", CheckAuth(getQuestions))
	mux.HandleFunc("/submit", CheckAuth(submitAnswer))
	mux.HandleFunc("/teacher/create", CheckAuthAndRole([]string{"teacher", "admin"}, createQuestion))

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("Server starting on port %s", port)
	// Важно: вызываем corsMiddleware здесь
	log.Fatal(http.ListenAndServe(":"+port, corsMiddleware(mux)))
}

// --- MIDDLEWARE ---

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// --- HANDLERS ---

func getQuestions(w http.ResponseWriter, r *http.Request) {
	courseID := r.Context().Value("course_id").(int)
	questions, err := GetQuestionsByCourse(courseID) // Из database.go
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(questions)
}

func submitAnswer(w http.ResponseWriter, r *http.Request) {
	var req struct {
		QuestionID int `json:"question_id"`
		Score      int `json:"score"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}

	userID := r.Context().Value("user_id").(int)
	courseID := r.Context().Value("course_id").(int)

	if err := SaveUserResult(userID, courseID, req.Score); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)
}

func createQuestion(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Text    string   `json:"text"`
		Options []string `json:"options"`
		Correct int      `json:"correct"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}

	id, err := CreateQuestion(req.Text, req.Options, req.Correct)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusCreated)
	fmt.Fprintf(w, `{"id": %d}`, id)
}
