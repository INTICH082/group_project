package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"os"

	_ "github.com/lib/pq" // Драйвер для PostgreSQL
)

var db *sql.DB

// InitDB подключается к Neon через переменную окружения
func InitDB() {
	connStr := os.Getenv("DATABASE_URL")
	if connStr == "" {
		log.Fatal("ОШИБКА: Переменная DATABASE_URL не установлена")
	}

	var err error
	db, err = sql.Open("postgres", connStr)
	if err != nil {
		log.Fatal("Ошибка конфигурации базы:", err)
	}

	// Проверка соединения
	if err = db.Ping(); err != nil {
		log.Fatal("База недоступна:", err)
	}
	log.Println("--- Успешное подключение к Neon DB ---")
}

// GetQuestionsByCourse возвращает вопросы для конкретного курса
func GetQuestionsByCourse(courseID int) ([]map[string]interface{}, error) {
	if db == nil {
		return nil, fmt.Errorf("соединение с БД не инициализировано")
	}

	query := `
		SELECT q.id, q.text, q.options 
		FROM questions q
		JOIN course_questions cq ON q.id = cq.question_id
		WHERE cq.course_id = $1`

	rows, err := db.Query(query, courseID)
	if err != nil {
		log.Printf("DB Query Error (courseID %d): %v", courseID, err)
		return nil, err
	}
	defer rows.Close()

	// Используем пустой срез вместо nil, чтобы JSON-ответ был [] вместо null
	questions := []map[string]interface{}{}

	for rows.Next() {
		var id int
		var text string
		var optionsJSON []byte

		if err := rows.Scan(&id, &text, &optionsJSON); err != nil {
			log.Printf("Scan Error: %v", err)
			continue
		}

		var options []string
		if err := json.Unmarshal(optionsJSON, &options); err != nil {
			log.Printf("JSON Unmarshal Error for ID %d: %v", id, err)
			options = []string{"ошибка загрузки вариантов"}
		}

		questions = append(questions, map[string]interface{}{
			"id":      id,
			"text":    text,
			"options": options,
		})
	}

	return questions, nil
}

// SaveUserResult сохраняет балл пользователя за курс
func SaveUserResult(userID int, courseID int, score int) error {
	if db == nil {
		return fmt.Errorf("соединение с БД не инициализировано")
	}

	// SQL запрос для вставки или обновления (UPSERT)
	// Если хочешь сохранять историю, просто убери ON CONFLICT и всё после него
	query := `
		INSERT INTO results (user_id, course_id, score, created_at) 
		VALUES ($1, $2, $3, NOW())
		ON CONFLICT (user_id, course_id) 
		DO UPDATE SET score = EXCLUDED.score, created_at = NOW()`

	_, err := db.Exec(query, userID, courseID, score)
	if err != nil {
		log.Printf("DB Save Error (User: %d, Course: %d): %v", userID, courseID, err)
	}
	return err
}

// CreateQuestion добавляет новый вопрос в банк данных
func CreateQuestion(text string, options []string, correctAnswer int) (int, error) {
	if db == nil {
		return 0, fmt.Errorf("соединение с БД не инициализировано")
	}

	optionsJSON, err := json.Marshal(options)
	if err != nil {
		return 0, fmt.Errorf("ошибка маршалинга опций: %v", err)
	}

	var lastID int
	query := `
		INSERT INTO questions (text, options, correct_answer) 
		VALUES ($1, $2, $3) RETURNING id`

	err = db.QueryRow(query, text, optionsJSON, correctAnswer).Scan(&lastID)
	if err != nil {
		log.Printf("DB Create Question Error: %v", err)
		return 0, err
	}

	return lastID, nil
}
