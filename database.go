package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	_ "github.com/lib/pq"
)

var db *sql.DB

func InitDB() {
	connStr := os.Getenv("DATABASE_URL")
	if connStr == "" {
		log.Fatal("ОШИБКА: DATABASE_URL не установлена")
	}

	var err error
	db, err = sql.Open("postgres", connStr)
	if err != nil {
		log.Fatal("Ошибка конфигурации базы:", err)
	}

	// --- ТВОИ НОВЫЕ НАСТРОЙКИ ДЛЯ СТАБИЛЬНОСТИ ---
	db.SetMaxOpenConns(25)                 // Макс. кол-во активных соединений
	db.SetMaxIdleConns(5)                  // Сколько держать "про запас"
	db.SetConnMaxLifetime(5 * time.Minute) // Пересоздавать соединение каждые 5 мин
	// ---------------------------------------------

	if err = db.Ping(); err != nil {
		log.Fatal("База недоступна:", err)
	}
	log.Println("--- Успешное подключение к Neon DB ---")
}

func GetQuestionsByCourse(courseID int) ([]map[string]interface{}, error) {
	if db == nil {
		return nil, fmt.Errorf("соединение с БД не инициализировано")
	}

	query := `
		SELECT q.id, q.text, q.options 
		FROM questions q
		JOIN course_questions cq ON q.id = cq.question_id
		WHERE cq.course_id = $1
		ORDER BY q.id ASC` // Добавил сортировку, чтобы вопросы не прыгали

	rows, err := db.Query(query, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	questions := []map[string]interface{}{}

	for rows.Next() {
		var id int
		var text string
		var optionsJSON []byte

		if err := rows.Scan(&id, &text, &optionsJSON); err != nil {
			continue
		}

		var options []string
		// Проверка на пустой JSON или NULL
		if len(optionsJSON) > 0 {
			json.Unmarshal(optionsJSON, &options)
		} else {
			options = []string{}
		}

		questions = append(questions, map[string]interface{}{
			"id":      id,
			"text":    text,
			"options": options,
		})
	}

	return questions, nil
}

func SaveUserResult(userID int, courseID int, score int) error {
	if db == nil {
		return fmt.Errorf("database connection is nil")
	}

	query := `
		INSERT INTO results (user_id, course_id, score, created_at) 
		VALUES ($1, $2, $3, NOW())
		ON CONFLICT (user_id, course_id) 
		DO UPDATE SET score = EXCLUDED.score, created_at = NOW()`

	_, err := db.Exec(query, userID, courseID, score)
	return err
}

func CreateQuestion(courseID int, text string, options []string, correctAnswer int) (int, error) {
	if db == nil {
		return 0, fmt.Errorf("соединение с БД не инициализировано")
	}

	optionsJSON, _ := json.Marshal(options)

	tx, err := db.Begin()
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()

	var lastID int
	queryInsertQuestion := `INSERT INTO questions (text, options, correct_answer) VALUES ($1, $2, $3) RETURNING id`

	err = tx.QueryRow(queryInsertQuestion, text, optionsJSON, correctAnswer).Scan(&lastID)
	if err != nil {
		return 0, err
	}

	queryLinkCourse := `INSERT INTO course_questions (course_id, question_id) VALUES ($1, $2)`
	_, err = tx.Exec(queryLinkCourse, courseID, lastID)
	if err != nil {
		return 0, err
	}

	err = tx.Commit()
	return lastID, err
}

func DeleteQuestion(questionID int) error {
	if db == nil {
		return fmt.Errorf("соединение с БД не инициализировано")
	}

	// Сначала проверяем, есть ли такой вопрос вообще (необязательно, но для чистоты логов ок)
	query := `DELETE FROM questions WHERE id = $1`
	result, err := db.Exec(query, questionID)
	if err != nil {
		return err
	}

	rowsAffected, _ := result.RowsAffected()
	if rowsAffected == 0 {
		return fmt.Errorf("вопрос %d не найден", questionID)
	}

	return nil
}
