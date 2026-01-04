package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
)

// CORS Middleware: Разрешает браузерам (JS) делать запросы к твоему API
func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Разрешаем доступ с любых доменов (*)
		w.Header().Set("Access-Control-Allow-Origin", "*")
		// Разрешаем стандартные методы HTTP
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		// Разрешаем передачу заголовков Content-Type и Authorization (для JWT)
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		// Если это предзапрос OPTIONS от браузера, сразу отвечаем 200 OK
		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func main() {
	InitDB()

	// Используем ServeMux для более удобного управления маршрутами
	mux := http.NewServeMux()

	// Регистрация маршрутов
	mux.HandleFunc("/course/", CheckAuth(getCourseQuestions))
	mux.HandleFunc("/course/add-question/", CheckAuthAndRole([]string{"teacher", "admin"}, addQuestionToCourse))
	mux.HandleFunc("/answer", CheckAuth(checkAnswer))
	mux.HandleFunc("/question", CheckAuthAndRole([]string{"teacher", "admin"}, createQuestion))
	mux.HandleFunc("/user/", CheckAuthAndRole([]string{"admin"}, changeUserRole))

	// Получаем порт от Render или используем 8080 локально
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("Server started on port %s", port)

	// Оборачиваем весь наш mux (роутер) в CORS Middleware
	log.Fatal(http.ListenAndServe(":"+port, corsMiddleware(mux)))
}

// --- Обработчики (Handlers) ---

func getCourseQuestions(w http.ResponseWriter, r *http.Request) {
	pathParts := strings.Split(r.URL.Path, "/")
	if len(pathParts) < 3 {
		http.Error(w, "Invalid URL format", http.StatusBadRequest)
		return
	}

	courseIDStr := pathParts[2]
	courseID, err := strconv.Atoi(courseIDStr)
	if err != nil {
		http.Error(w, "Invalid course ID", http.StatusBadRequest)
		return
	}

	questions, err := GetQuestionsForCourse(courseID)
	if err != nil {
		http.Error(w, "Failed to get questions: "+err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(questions)
}

func checkAnswer(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req struct {
		QuestionID int `json:"question_id"`
		UserAnswer int `json:"user_answer"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	userID := r.Context().Value("user_id").(int)
	result, err := CheckUserAnswer(userID, req.QuestionID, req.UserAnswer)
	if err != nil {
		http.Error(w, "Failed to check answer: "+err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func createQuestion(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req struct {
		Text          string   `json:"text"`
		Options       []string `json:"options"`
		CorrectAnswer int      `json:"correct_answer"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if len(req.Options) < 2 {
		http.Error(w, "At least 2 options required", http.StatusBadRequest)
		return
	}

	if req.CorrectAnswer < 0 || req.CorrectAnswer >= len(req.Options) {
		http.Error(w, "Invalid correct answer index", http.StatusBadRequest)
		return
	}

	authorID := r.Context().Value("user_id").(int)
	questionID, err := CreateQuestion(req.Text, req.Options, req.CorrectAnswer, authorID)
	if err != nil {
		http.Error(w, "Failed to create question: "+err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]int{"question_id": questionID})
}

func addQuestionToCourse(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req struct {
		CourseID   int `json:"course_id"`
		QuestionID int `json:"question_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if err := AddQuestionToCourse(req.CourseID, req.QuestionID); err != nil {
		http.Error(w, "Failed to add question to course: "+err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusCreated)
}

func changeUserRole(w http.ResponseWriter, r *http.Request) {
	pathParts := strings.Split(r.URL.Path, "/")
	if len(pathParts) < 4 {
		http.Error(w, "Invalid URL format", http.StatusBadRequest)
		return
	}

	userIDStr := pathParts[2]
	userID, err := strconv.Atoi(userIDStr)
	if err != nil {
		http.Error(w, "Invalid user ID", http.StatusBadRequest)
		return
	}

	var req struct {
		Role string `json:"role"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	validRoles := map[string]bool{
		"student": true,
		"teacher": true,
		"admin":   true,
	}

	if !validRoles[req.Role] {
		http.Error(w, "Invalid role. Must be 'student', 'teacher', or 'admin'", http.StatusBadRequest)
		return
	}

	if err := ChangeUserRole(userID, req.Role); err != nil {
		http.Error(w, "Failed to change user role: "+err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
}
