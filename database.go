package main

import (
	"database/sql"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"

	_ "github.com/jackc/pgx/v5/stdlib"
)

var db *sql.DB

func InitDB() {
	// 1. Пытаемся взять URL из системы (для Render/Railway)
	// 2. Если пусто — используем вашу новую строку от Neon
	connStr := os.Getenv("DATABASE_URL")
	if connStr == "" {
		connStr = "postgresql://neondb_owner:npg_Sw1LVdo0JOpM@ep-soft-dust-adz0kss6-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"
	}

	var err error
	db, err = sql.Open("pgx", connStr)
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}

	if err = db.Ping(); err != nil {
		log.Fatalf("Database connection failed: %v", err)
	}

	log.Println("Connected to Neon Cloud Database successfully!")
}

func GetQuestionsForCourse(courseID int) ([]map[string]interface{}, error) {
	rows, err := db.Query(`
		SELECT q.id, q.text, q.options
		FROM questions q
		JOIN course_questions cq ON q.id = cq.question_id
		WHERE cq.course_id = $1 AND q.is_active = true
	`, courseID)

	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var questions []map[string]interface{}
	for rows.Next() {
		var id int
		var text string
		var optionsStr string // Временно читаем как строку

		if err := rows.Scan(&id, &text, &optionsStr); err != nil {
			return nil, err
		}

		// Преобразуем строку PostgreSQL массива в Go массив
		options := parsePostgresArray(optionsStr)

		questions = append(questions, map[string]interface{}{
			"id":      id,
			"text":    text,
			"options": options,
		})
	}

	return questions, nil
}
func CheckUserAnswer(userID, questionID, userAnswer int) (map[string]interface{}, error) {
	var correctAnswer int
	err := db.QueryRow(`
		SELECT correct_answer 
		FROM questions 
		WHERE id = $1 AND is_active = true
	`, questionID).Scan(&correctAnswer)

	if err != nil {
		return nil, err
	}

	isCorrect := (userAnswer == correctAnswer)

	_, err = db.Exec(`
		INSERT INTO results (user_id, question_id, user_answer, is_correct)
		VALUES ($1, $2, $3, $4)
	`, userID, questionID, userAnswer, isCorrect)

	if err != nil {
		return nil, err
	}

	result := map[string]interface{}{
		"question_id":    questionID,
		"user_answer":    userAnswer,
		"correct_answer": correctAnswer,
		"is_correct":     isCorrect,
	}

	if isCorrect {
		result["message"] = "Правильно! Отличная работа!"
	} else {
		result["message"] = "Неправильно. Попробуй еще раз!"
	}

	return result, nil
}

func CreateQuestion(text string, options []string, correctAnswer, authorID int) (int, error) {
	var id int
	err := db.QueryRow(`
		INSERT INTO questions (text, options, correct_answer, author_id)
		VALUES ($1, $2, $3, $4)
		RETURNING id
	`, text, options, correctAnswer, authorID).Scan(&id)

	return id, err
}

// Обработчик: добавить вопрос в курс (только teacher/admin)
func АddQuestionToCourse(w http.ResponseWriter, r *http.Request) {
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
func AddQuestionToCourse(courseID, questionID int) error {
	_, err := db.Exec(`
		INSERT INTO course_questions (course_id, question_id)
		VALUES ($1, $2)
		ON CONFLICT DO NOTHING
	`, courseID, questionID)
	return err
}
func ChangeUserRole(userID int, newRole string) error {
	_, err := db.Exec(`
		UPDATE users 
		SET role = $1 
		WHERE id = $2
	`, newRole, userID)

	return err
}
func parsePostgresArray(s string) []string {
	// Удаляем фигурные скобки и разделяем по запятым
	s = strings.Trim(s, "{}")
	if s == "" {
		return []string{}
	}

	// Разделяем по запятым, но учитываем, что в опциях могут быть запятые в кавычках
	parts := strings.Split(s, ",")
	result := make([]string, 0, len(parts))

	for _, part := range parts {
		// Удаляем кавычки и лишние пробелы
		part = strings.Trim(part, `"`)
		part = strings.TrimSpace(part)
		if part != "" {
			result = append(result, part)
		}
	}

	return result
}
