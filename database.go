package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/lib/pq"
	_ "github.com/lib/pq"
)

var db *sql.DB

func InitDB() {
	connStr := os.Getenv("DATABASE_URL")
	if connStr == "" {
		log.Fatal("DATABASE_URL is missing")
	}

	var err error
	db, err = sql.Open("postgres", connStr)
	if err != nil {
		log.Fatal(err)
	}

	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	if err = db.Ping(); err != nil {
		log.Fatal("Database unreachable:", err)
	}
	log.Println("--- Database initialized with New Structure ---")
}

// --- ЛОГИКА ВОПРОСОВ (ВЕРСИОННОСТЬ) ---

func CreateQuestion(title string, text string, options []string, correct int, authorID int) (int, error) {
	optionsJSON, err := json.Marshal(options)
	if err != nil {
		return 0, fmt.Errorf("marshal options: %v", err)
	}

	// Используем COALESCE, чтобы если таблица пуста, вернулся 1, а не ошибка
	var nextID int
	queryID := "SELECT COALESCE(MAX(id), 0) + 1 FROM questions"
	err = db.QueryRow(queryID).Scan(&nextID)
	if err != nil {
		log.Printf("QueryRow MAX(id) error: %v", err)
		return 0, err
	}

	// ВАЖНО: Добавил поле title, так как оно есть в твоем списке колонок!
	query := `INSERT INTO questions (id, version, title, text, options, correct_option, author_id) 
              VALUES ($1, 1, $2, $3, $4, $5, $6) RETURNING id`

	var id int
	err = db.QueryRow(query, nextID, title, text, optionsJSON, correct, authorID).Scan(&id)
	if err != nil {
		log.Printf("Insert question error: %v", err)
		return 0, err
	}
	return id, nil
}

func UpdateQuestion(questionID int, text string, options []string, correct int) error {
	// ТЗ требует: при изменении создаем новую версию
	var currentVersion int
	err := db.QueryRow("SELECT MAX(version) FROM questions WHERE id = $1", questionID).Scan(&currentVersion)
	if err != nil {
		return err
	}

	optionsJSON, _ := json.Marshal(options)
	query := `INSERT INTO questions (id, version, text, options, correct_option, author_id) 
              SELECT id, $2, $3, $4, $5, author_id FROM questions 
              WHERE id = $1 AND version = $6`

	_, err = db.Exec(query, questionID, currentVersion+1, text, optionsJSON, correct, currentVersion)
	return err
}

// --- ЛОГИКА ПОПЫТОК (START TEST) ---

func StartAttempt(userID int, testID int) (int, error) {
	// 1. Получаем список актуальных версий вопросов для этого теста
	// В ТЗ: при создании попытки замораживаем версии
	queryVersions := `
		SELECT q.id, MAX(q.version) 
		FROM questions q
		JOIN (SELECT unnest(question_ids) as qid FROM tests WHERE id = $1) t ON q.id = t.qid
		WHERE q.is_deleted = false
		GROUP BY q.id`

	rows, err := db.Query(queryVersions, testID)
	if err != nil {
		return 0, err
	}
	defer rows.Close()

	versionsMap := make(map[int]int)
	for rows.Next() {
		var qid, v int
		rows.Scan(&qid, &v)
		versionsMap[qid] = v
	}
	versionsJSON, _ := json.Marshal(versionsMap)

	// 2. Создаем запись попытки
	var attemptID int
	err = db.QueryRow(`INSERT INTO attempts (user_id, test_id, question_versions) 
                       VALUES ($1, $2, $3) RETURNING id`,
		userID, testID, versionsJSON).Scan(&attemptID)
	if err != nil {
		return 0, err
	}

	// 3. Создаем пустые ответы для каждого вопроса (selected_option = -1)
	for qid, v := range versionsMap {
		db.Exec(`INSERT INTO user_answers (attempt_id, question_id, question_version) 
                 VALUES ($1, $2, $3)`, attemptID, qid, v)
	}

	return attemptID, nil
}

// --- ЛОГИКА ОТВЕТОВ ---

func SubmitAnswer(attemptID int, questionID int, selectedOption int) error {
	// Проверяем, не завершена ли попытка
	var status string
	db.QueryRow("SELECT status FROM attempts WHERE id = $1", attemptID).Scan(&status)
	if status == "completed" {
		return fmt.Errorf("attempt already completed")
	}

	_, err := db.Exec(`UPDATE user_answers SET selected_option = $1 
                       WHERE attempt_id = $2 AND question_id = $3`,
		selectedOption, attemptID, questionID)
	return err
}
func CreateTest(courseID int, name string, questionIDs []int) (int, error) {
	// Мы перечисляем 4 колонки:
	// 1. course_id
	// 2. name
	// 3. question_ids (массив в Postgres)
	// 4. is_active (сразу ставим true)
	// Поле id заполнится само (SERIAL), поле is_deleted по умолчанию false.

	query := `
		INSERT INTO tests (course_id, name, question_ids, is_active) 
		VALUES ($1, $2, $3, $4) 
		RETURNING id`

	var id int

	// Передаем ровно 4 аргумента для 4 колонок:
	err := db.QueryRow(
		query,
		courseID,              // $1
		name,                  // $2
		pq.Array(questionIDs), // $3 (превращает []int в {1,2,3} для Postgres)
		true,                  // $4
	).Scan(&id)

	if err != nil {
		// Логируем ошибку, чтобы её было видно в консоли Render
		log.Printf("❌ Ошибка в CreateTest: %v", err)
		return 0, err
	}

	log.Printf("✅ Тест успешно создан с ID: %d", id)
	return id, nil
}
