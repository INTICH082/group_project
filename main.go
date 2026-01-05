package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

var jwtKey = []byte("iplaygodotandclaimfun")

// MyCustomClaims согласно ТЗ
type MyCustomClaims struct {
	UserID      int      `json:"user_id"`
	Role        string   `json:"role"`
	Permissions []string `json:"permissions"`
	IsBlocked   bool     `json:"is_blocked"`
	jwt.RegisteredClaims
}

// --- MIDDLEWARE (Критически важно по ТЗ) ---

func AuthMiddleware(requiredPermission string, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" {
			http.Error(w, "Missing token", http.StatusUnauthorized)
			return
		}

		tokenString := strings.TrimPrefix(authHeader, "Bearer ")
		claims := &MyCustomClaims{}

		token, err := jwt.ParseWithClaims(tokenString, claims, func(token *jwt.Token) (interface{}, error) {
			return jwtKey, nil
		})

		if err != nil || !token.Valid {
			http.Error(w, "Invalid token", http.StatusUnauthorized)
			return
		}

		// ТЗ: "Для пользователя запрещены все действия... отвечать кодом 418"
		if claims.IsBlocked {
			w.WriteHeader(http.StatusTeapot)
			fmt.Fprint(w, "I'm a teapot (User is blocked)")
			return
		}

		// Проверка разрешений
		if requiredPermission != "" {
			hasPerm := false
			for _, p := range claims.Permissions {
				if p == requiredPermission {
					hasPerm = true
					break
				}
			}
			if !hasPerm {
				http.Error(w, "Forbidden: "+requiredPermission, http.StatusForbidden)
				return
			}
		}

		// Передаем UserID через контекст, чтобы хендлеры его видели
		ctx := context.WithValue(r.Context(), "user_id", claims.UserID)
		next.ServeHTTP(w, r.WithContext(ctx))
	}
}

// --- ХЕНДЛЕРЫ ---

func CreateQuestionHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Title   string   `json:"title"`
		Text    string   `json:"text"`
		Options []string `json:"options"`
		Correct int      `json:"correct_option"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad JSON", http.StatusBadRequest)
		return
	}

	// Берем ID автора из контекста (из токена)
	authorID := r.Context().Value("user_id").(int)
	id, err := CreateQuestion(req.Title, req.Text, req.Options, req.Correct, authorID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]int{"id": id})
}

// ТЗ: Активировать/Деактивировать тест
func UpdateTestStatusHandler(w http.ResponseWriter, r *http.Request) {
	testID, _ := strconv.Atoi(r.URL.Query().Get("id"))
	active, _ := strconv.ParseBool(r.URL.Query().Get("active"))

	err := SetTestStatus(testID, active)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	fmt.Fprint(w, "Test status updated")
}

func StartTestHandler(w http.ResponseWriter, r *http.Request) {
	userID := r.Context().Value("user_id").(int)
	testID, _ := strconv.Atoi(r.URL.Query().Get("test_id"))

	attemptID, err := StartAttempt(userID, testID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]int{"attempt_id": attemptID})
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
func SubmitAnswerHandler(w http.ResponseWriter, r *http.Request) {
	attemptID, _ := strconv.Atoi(r.URL.Query().Get("attempt_id"))
	questionID, _ := strconv.Atoi(r.URL.Query().Get("question_id"))

	var req struct {
		Option int `json:"option"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad JSON", http.StatusBadRequest)
		return
	}

	// Вызываем функцию из твоего database.go
	err := SubmitAnswer(attemptID, questionID, req.Option)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	fmt.Fprint(w, "OK")
}

func main() {
	InitDB()
	mux := http.NewServeMux()

	// Настройка ручек с Middleware согласно ТЗ
	mux.HandleFunc("/teacher/question/create", AuthMiddleware("quest:create", CreateQuestionHandler))
	mux.HandleFunc("/teacher/test/create", AuthMiddleware("course:test:add", CreateTestHandler))
	mux.HandleFunc("/teacher/test/status", AuthMiddleware("course:test:write", UpdateTestStatusHandler))

	mux.HandleFunc("/test/start", AuthMiddleware("", StartTestHandler))
	mux.HandleFunc("/test/answer", AuthMiddleware("", SubmitAnswerHandler))
	mux.HandleFunc("/test/finish", AuthMiddleware("", FinishTestHandler))

	log.Println("🚀 Full API started on :8080")
	http.ListenAndServe(":8080", mux)
}
