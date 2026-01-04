package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
)

func main() {
	// 1. Инициализация БД (функция должна быть в database.go)
	InitDB()

	// 2. Создаем стандартный маршрутизатор
	mux := http.NewServeMux()

	// --- МАРШРУТЫ ---
	// Студенческие эндпоинты
	mux.HandleFunc("/questions", CheckAuth(getQuestions))
	mux.HandleFunc("/submit", CheckAuth(submitAnswer))

	// Учительские эндпоинты (с проверкой ролей)
	mux.HandleFunc("/teacher/create", CheckAuthAndRole([]string{"teacher", "admin"}, createQuestion))
	mux.HandleFunc("/teacher/delete", CheckAuthAndRole([]string{"teacher", "admin"}, deleteQuestionHandler))

	// 3. Настройка порта
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	// 4. Запуск сервера с CORS middleware
	// Важно: corsMiddleware должен оборачивать mux, чтобы обрабатывать OPTIONS запросы до аутентификации
	log.Printf("🚀 Server starting on port %s", port)
	err := http.ListenAndServe(":"+port, corsMiddleware(mux))
	if err != nil {
		log.Fatal("❌ Server failed to start: ", err)
	}
}

// --- MIDDLEWARE ---

// corsMiddleware исправляет проблемы доступа с фронтенда (браузеров)
func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Разрешаем доступ всем (можно заменить на конкретный домен позже)
		w.Header().Set("Access-Control-Allow-Origin", "*")
		// Добавляем DELETE в список разрешенных методов
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
		// Разрешаем заголовки, важные для JWT и JSON
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		// Если браузер спрашивает разрешение (preflight), отвечаем 200 OK
		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		next.ServeHTTP(w, r)
	})
}

// --- HANDLERS (Обработчики) ---

func getQuestions(w http.ResponseWriter, r *http.Request) {
	val := r.Context().Value("course_id")
	courseID, ok := val.(int)
	if !ok {
		http.Error(w, "Invalid course ID", http.StatusBadRequest)
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

	userID, okU := r.Context().Value("user_id").(int)
	courseID, okC := r.Context().Value("course_id").(int)

	if !okU || !okC {
		http.Error(w, "Auth data missing", http.StatusUnauthorized)
		return
	}

	if err := SaveUserResult(userID, courseID, req.Score); err != nil {
		http.Error(w, "Failed to save result", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
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

	courseID, ok := r.Context().Value("course_id").(int)
	if !ok {
		http.Error(w, "Course ID missing", http.StatusUnauthorized)
		return
	}

	id, err := CreateQuestion(courseID, req.Text, req.Options, req.Correct)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	fmt.Fprintf(w, `{"id": %d, "message": "Question created"}`, id)
}

func deleteQuestionHandler(w http.ResponseWriter, r *http.Request) {
	idStr := r.URL.Query().Get("id")
	if idStr == "" {
		http.Error(w, "ID missing", http.StatusBadRequest)
		return
	}

	var id int
	if _, err := fmt.Sscanf(idStr, "%d", &id); err != nil {
		http.Error(w, "Invalid ID format", http.StatusBadRequest)
		return
	}

	if err := DeleteQuestion(id); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintf(w, `{"message": "Question %d deleted"}`, id)
}
