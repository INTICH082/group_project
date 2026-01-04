package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
)

func main() {
	InitDB() // Подключение к Neon

	mux := http.NewServeMux()

	// Студент просто просит "мои вопросы", а сервер сам знает какой курс из токена
	mux.HandleFunc("/questions", CheckAuth(getQuestions))

	// Студент просто шлет ответ, сервер знает кто он и на какой курс отвечает
	mux.HandleFunc("/submit", CheckAuth(submitAnswer))

	// Учитель создает вопрос (в базу вопросов)
	mux.HandleFunc("/teacher/create", CheckAuthAndRole([]string{"teacher", "admin"}, createQuestion))

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("API упрощен и запущен на порту %s", port)
	log.Fatal(http.ListenAndServe(":"+port, corsMiddleware(mux)))
}

// Пример функции получения вопросов
func getQuestions(w http.ResponseWriter, r *http.Request) {
	// Достаем course_id, который положил туда Middleware
	courseID := r.Context().Value("course_id").(int)

	// Делаем запрос в базу только по этому courseID
	questions, err := GetQuestionsByCourse(courseID)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(questions)
}
