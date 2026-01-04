package main

import (
	"database/sql"
	"encoding/json"
	"log"
	"os"

	_ "github.com/lib/pq" // Драйвер для PostgreSQL
)

var db *sql.DB

// InitDB подключается к Neon
func InitDB() {
	connStr := os.Getenv("DATABASE_URL")
	var err error
	db, err = sql.Open("postgres", connStr)
	if err != nil {
		log.Fatal("Ошибка подключения к базе:", err)
	}

	if err = db.Ping(); err != nil {
		log.Fatal("База недоступна:", err)
	}
	log.Println("Успешное подключение к Neon DB")
}

// 1. Получение вопросов именно для того курса, который указан в токене
func GetQuestionsByCourse(courseID int) ([]map[string]interface{}, error) {
	query := `
		SELECT q.id, q.text, q.options 
		FROM questions q
		JOIN course_questions cq ON q.id = cq.question_id
		WHERE cq.course_id = $1`

	rows, err := db.Query(query, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var questions []map[string]interface{}
	for rows.Next() {
		var id int
		var text string
		var optionsJSON []byte

		if err := rows.Scan(&id, &text, &optionsJSON); err != nil {
			return nil, err
		}

		var options []string
		json.Unmarshal(optionsJSON, &options)

		questions = append(questions, map[string]interface{}{
			"id":      id,
			"text":    text,
			"options": options,
		})
	}
	return questions, nil
}

// 2. Сохранение результата (используем user_id и course_id из токена)
func SaveUserResult(userID int, courseID int, score int) error {
	query := `
		INSERT INTO results (user_id, course_id, score) 
		VALUES ($1, $2, $3)`

	_, err := db.Exec(query, userID, courseID, score)
	return err
}

// 3. Создание вопроса учителем (только в общий банк)
func CreateQuestion(text string, options []string, correctAnswer int) (int, error) {
	optionsJSON, _ := json.Marshal(options)
	var lastID int
	query := `
		INSERT INTO questions (text, options, correct_answer) 
		VALUES ($1, $2, $3) RETURNING id`

	err := db.QueryRow(query, text, optionsJSON, correctAnswer).Scan(&lastID)
	return lastID, err
}
