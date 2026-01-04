package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"

	"github.com/golang-jwt/jwt/v5"
)

var jwtKey = []byte("iplaygodotandclaimfun")

// Структура токена согласно ТЗ
type MyCustomClaims struct {
	UserID      int      `json:"user_id"`
	Role        string   `json:"role"`
	Permissions []string `json:"permissions"`
	IsBlocked   bool     `json:"is_blocked"`
	jwt.RegisteredClaims
}

// --- DTO СТРУКТУРЫ ---

type CreateQuestionRequest struct {
	Title         string   `json:"title"`
	Text          string   `json:"text"`
	Options       []string `json:"options"`
	CorrectOption int      `json:"correct_option"`
}

type CreateTestRequest struct {
	CourseID    int    `json:"course_id"`
	Name        string `json:"name"`
	QuestionIDs []int  `json:"question_ids"`
}

type AnswerRequest struct {
	Option int `json:"option"`
}

// --- ХЕНДЛЕРЫ ---

func CreateQuestionHandler(w http.ResponseWriter, r *http.Request) {
	var req CreateQuestionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad JSON", http.StatusBadRequest)
		return
	}

	authorID, _ := strconv.Atoi(r.Header.Get("X-User-ID"))
	id, err := CreateQuestion(req.Title, req.Text, req.Options, req.CorrectOption, authorID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]int{"id": id})
}

func CreateTestHandler(w http.ResponseWriter, r *http.Request) {
	var req CreateTestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad JSON", http.StatusBadRequest)
		return
	}

	id, err := CreateTest(req.CourseID, req.Name, req.QuestionIDs)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]int{"id": id})
}

func StartTestHandler(w http.ResponseWriter, r *http.Request) {
	userID, _ := strconv.Atoi(r.Header.Get("X-User-ID"))
	testID, _ := strconv.Atoi(r.URL.Query().Get("test_id"))

	attemptID, err := StartAttempt(userID, testID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]int{"attempt_id": attemptID})
}

func SubmitAnswerHandler(w http.ResponseWriter, r *http.Request) {
	attemptID, _ := strconv.Atoi(r.URL.Query().Get("attempt_id"))
	questionID, _ := strconv.Atoi(r.URL.Query().Get("question_id"))

	var req AnswerRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad JSON", http.StatusBadRequest)
		return
	}

	err := SubmitAnswer(attemptID, questionID, req.Option)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	fmt.Fprint(w, "OK")
}

func FinishTestHandler(w http.ResponseWriter, r *http.Request) {
	attemptID, _ := strconv.Atoi(r.URL.Query().Get("attempt_id"))
	score, err := FinishAttempt(attemptID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status": "finished",
		"score":  fmt.Sprintf("%.2f%%", score),
	})
}

func main() {
	InitDB()
	mux := http.NewServeMux()

	// Учительские ручки
	mux.HandleFunc("/teacher/question/create", HasPermission("course:test:add", CreateQuestionHandler))
	mux.HandleFunc("/teacher/test/create", HasPermission("course:test:add", CreateTestHandler))

	// Студенческие ручки
	mux.HandleFunc("/test/start", HasPermission("", StartTestHandler))
	mux.HandleFunc("/test/answer", HasPermission("", SubmitAnswerHandler))
	mux.HandleFunc("/test/finish", HasPermission("", FinishTestHandler))

	mux.HandleFunc("/ping", func(w http.ResponseWriter, r *http.Request) { fmt.Fprint(w, "pong") })

	log.Println("🚀 Server started on :8080")
	http.ListenAndServe(":8080", mux)
}
