package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

// Секрет должен совпадать с секретом модуля авторизации
var jwtKey = []byte("iplaygodotandclaimfun")

// Структура токена согласно ТЗ
type MyCustomClaims struct {
	UserID      int      `json:"user_id"`
	Role        string   `json:"role"`
	Permissions []string `json:"permissions"` // Права: user:list:read, course:test:add и т.д.
	IsBlocked   bool     `json:"is_blocked"`  // Флаг для ответа 418
	jwt.RegisteredClaims
}

// --- СТРУКТУРЫ ДЛЯ ПРИЕМА JSON (DTO) ---

type CreateQuestionRequest struct {
	Text          string   `json:"text"`
	Options       []string `json:"options"`
	CorrectOption int      `json:"correct_option"`
}

type AnswerRequest struct {
	Option int `json:"option"`
}

// --- MIDDLEWARE ---

func AuthMiddleware(requiredPermission string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
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

			// 1. Проверка на блокировку [ТЗ: ответ 418]
			if claims.IsBlocked {
				w.WriteHeader(http.StatusTeapot) // 418 I'm a teapot
				fmt.Fprintf(w, "User is blocked")
				return
			}

			// 2. Проверка прав (RBAC)
			if requiredPermission != "" {
				hasPerm := false
				for _, p := range claims.Permissions {
					if p == requiredPermission {
						hasPerm = true
						break
					}
				}
				if !hasPerm {
					http.Error(w, "Forbidden: insufficient permissions", http.StatusForbidden)
					return
				}
			}

			// Передаем UserID в заголовке для использования в хендлерах
			r.Header.Set("X-User-ID", strconv.Itoa(claims.UserID))
			next.ServeHTTP(w, r)
		})
	}
}

// --- ОБРАБОТЧИКИ (HANDLERS) ---

// Создание вопроса (Преподаватель)
func CreateQuestionHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Use POST", http.StatusMethodNotAllowed)
		return
	}

	var req CreateQuestionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad JSON", http.StatusBadRequest)
		return
	}

	authorID, _ := strconv.Atoi(r.Header.Get("X-User-ID"))

	id, err := CreateQuestion(req.Text, req.Options, req.CorrectOption, authorID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]int{"id": id})
}

// Старт теста (Студент)
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

// Отправка ответа (Студент)
func SubmitAnswerHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Use POST", http.StatusMethodNotAllowed)
		return
	}

	attemptID, _ := strconv.Atoi(r.URL.Query().Get("attempt_id"))
	questionID, _ := strconv.Atoi(r.URL.Query().Get("question_id"))

	var req AnswerRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad JSON", http.StatusBadRequest)
		return
	}

	err := SubmitAnswer(attemptID, questionID, req.Option)
	if err != nil {
		http.Error(w, err.Error(), http.StatusForbidden)
		return
	}

	fmt.Fprint(w, "OK")
}

func main() {
	// Инициализируем БД (функция из database.go)
	InitDB()

	mux := http.NewServeMux()

	// --- МАРШРУТЫ СОГЛАСНО ТЗ ---

	// 1. Ресурс: Вопросы
	// Создание вопроса: доступ только с разрешением "course:test:add" [ТЗ: 618]
	mux.HandleFunc("/teacher/question/create", HasPermission("course:test:add", CreateQuestionHandler))

	// 2. Ресурс: Тесты / Попытки
	// Старт теста: доступ по умолчанию для любого авторизованного ("") [ТЗ: 662]
	mux.HandleFunc("/test/start", HasPermission("", StartTestHandler))

	// 3. Ресурс: Ответы
	// Сохранение/изменение ответа: доступ для того, кто проходит тест [ТЗ: 673]
	mux.HandleFunc("/test/answer", HasPermission("", SubmitAnswerHandler))

	// 4. Служебные эндпоинты
	mux.HandleFunc("/ping", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "pong")
	})

	// --- ЗАПУСК ---

	// Обернем весь mux в CORS middleware, если он у тебя был,
	// чтобы фронтенд мог достучаться до API
	log.Println("🚀 Main Module started on :8080")
	if err := http.ListenAndServe(":8080", mux); err != nil {
		log.Fatal(err)
	}
}
