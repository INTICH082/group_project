package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
)

func main() {
	InitDB() // Инициализация из database.go

	mux := http.NewServeMux()

	// Настройка маршрутов
	mux.HandleFunc("/questions", CheckAuth(getQuestions))
	mux.HandleFunc("/submit", CheckAuth(submitAnswer))
	mux.HandleFunc("/teacher/create", CheckAuthAndRole([]string{"teacher", "admin"}, createQuestion))
	mux.HandleFunc("/teacher/delete", CheckAuthAndRole([]string{"teacher", "admin"}, deleteQuestionHandler))
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("Server starting on port %s", port)
	// Оборачиваем mux в CORS для работы с фронтендом
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
	// Безопасное извлечение ID курса
	val := r.Context().Value("course_id")
	courseID, ok := val.(int)
	if !ok {
		http.Error(w, "Invalid course ID in context", http.StatusBadRequest)
		return
	}

	questions, err := GetQuestionsByCourse(courseID)
	if err != nil {
		http.Error(w, "DB Error: "+err.Error(), http.StatusInternalServerError)
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
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	// Извлекаем данные из контекста с проверкой типа
	uVal := r.Context().Value("user_id")
	cVal := r.Context().Value("course_id")

	userID, okU := uVal.(int)
	courseID, okC := cVal.(int)

	if !okU || !okC {
		http.Error(w, "Auth data missing", http.StatusUnauthorized)
		return
	}

	if err := SaveUserResult(userID, courseID, req.Score); err != nil {
		http.Error(w, "Failed to save result", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	fmt.Fprint(w, `{"status":"success"}`)
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

	// Достаем course_id из токена учителя
	val := r.Context().Value("course_id")
	courseID, ok := val.(int)
	if !ok {
		http.Error(w, "Course ID missing in token", http.StatusUnauthorized)
		return
	}

	// Вызываем обновленную функцию
	id, err := CreateQuestion(courseID, req.Text, req.Options, req.Correct)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	fmt.Fprintf(w, `{"id": %d, "message": "Question created and linked to course %d"}`, id, courseID)
}
func deleteQuestionHandler(w http.ResponseWriter, r *http.Request) {
	// Достаем ID из параметров URL
	idStr := r.URL.Query().Get("id")
	if idStr == "" {
		http.Error(w, "Укажите ID вопроса", http.StatusBadRequest)
		return
	}

	var id int
	fmt.Sscanf(idStr, "%d", &id)

	err := DeleteQuestion(id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, `{"message": "Question %d deleted"}`, id)
}
